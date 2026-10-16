"""Fuel-card portal provider — the source of real contract prices.

Status: the customer has not named their provider (Comdata / EFS-WEX / RTS / other)
and no credentials exist yet, so the portal-specific part cannot be written or
tested. Everything that does not depend on the portal is implemented and working:
session reuse, expiry detection, browser lifecycle, and the response-capture
strategy below.

How to finish this once credentials arrive — an hour of work, not a rewrite:

1. ``python -m app.scrapers.login_cli --provider contract_portal`` opens a visible
   browser. Log in, pass 2FA by hand. The session is saved to the database.
2. With the portal's fuel map open, watch the network panel. These maps almost
   always load their pins from one JSON endpoint. Put its URL fragment in
   ``CONTRACT_PORTAL_MAP_API_PATTERN`` (e.g. ``/api/locations/search``).
3. Run this provider once with ``dump_payloads=True``; it saves the captured JSON
   next to the scraper state so the shape can be inspected.
4. Fill in :func:`parse_portal_payload` to map that JSON onto ``StationRecord`` and
   ``PriceRecord``. That is the only portal-specific code in the system.

Capturing the XHR is deliberate rather than reading the rendered DOM: map widgets
render pins to a canvas or to virtualized markers where prices only appear in a
popup on click, so DOM scraping means thousands of clicks and breaks on every CSS
change. The JSON payload has everything at once and changes far less often.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.services.fuel.base import (
    FuelPriceProvider,
    FuelPriceUnavailable,
    NeedsLogin,
    PriceRecord,
    StationRecord,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "contract_portal"


class PortalPayloadNotMapped(FuelPriceUnavailable):
    """Payload captured, but nobody has mapped its fields yet (step 4 above)."""


def parse_portal_payload(
    payloads: list[dict[str, Any]], as_of: date
) -> tuple[list[StationRecord], list[PriceRecord]]:
    """Map captured portal JSON onto our records.

    Implement this when the portal is known. A typical payload looks like::

        {"locations": [{"siteId": "12345", "name": "...", "state": "TX",
                        "latitude": 32.1, "longitude": -96.5,
                        "fuelPrices": [{"product": "DSL", "price": 3.499}]}]}

    Two rules that matter more than the field names:

    * ``is_contract_price=True`` belongs only on prices that really are the
      company's negotiated price. If the portal shows a retail price alongside,
      do not conflate them — the entire savings figure depends on this.
    * Keep the portal's own site id as ``external_id``, so prices continue to line
      up with stations across refreshes.
    """
    raise PortalPayloadNotMapped(
        f"Captured {len(payloads)} payload(s) from the portal, but "
        "parse_portal_payload() has not been implemented for this provider yet. "
        "See the module docstring, step 4."
    )


class ContractPortalProvider(FuelPriceProvider):
    name = PROVIDER_NAME
    contract_prices = True

    def __init__(
        self,
        storage_state: dict[str, Any] | None,
        settings: Settings | None = None,
        as_of: date | None = None,
        dump_payloads: bool = False,
    ):
        self.settings = settings or get_settings()
        self.storage_state = storage_state
        self._as_of = as_of
        self._dump_payloads = dump_payloads
        self._cache: tuple[list[StationRecord], list[PriceRecord]] | None = None

    def _require_config(self) -> None:
        if not self.settings.contract_portal_url:
            raise NeedsLogin(
                "CONTRACT_PORTAL_URL is not configured. Until the customer provides "
                "the fuel-card portal and credentials, run with "
                "FUEL_PRICE_PROVIDER=public_eia or seed."
            )
        if self.storage_state is None:
            raise NeedsLogin(
                "No saved browser session for the fuel-card portal. Run "
                "`python -m app.scrapers.login_cli --provider contract_portal` "
                "and pass 2FA by hand once."
            )

    async def _capture(self) -> list[dict[str, Any]]:
        """Open the portal with the saved session and collect the map's JSON."""
        self._require_config()
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - depends on the image
            raise FuelPriceUnavailable(
                "Playwright is not installed in this image; the portal scraper "
                "cannot run. `pip install playwright && playwright install chromium`"
            ) from exc

        from app.scrapers.session import looks_like_login_page

        pattern = self.settings.contract_portal_map_api_pattern
        payloads: list[dict[str, Any]] = []

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=self.storage_state)
            page = await context.new_page()

            async def on_response(response) -> None:
                if pattern and pattern in response.url and response.status == 200:
                    try:
                        payloads.append(await response.json())
                    except Exception:  # noqa: BLE001 - a non-JSON match is not fatal
                        logger.debug("matched %s but body was not JSON", response.url)

            page.on("response", on_response)

            try:
                await page.goto(self.settings.contract_portal_url, wait_until="networkidle")
                content = await page.content()
                if looks_like_login_page(page.url, content):
                    raise NeedsLogin(
                        "The portal redirected to its login page: the saved session "
                        "has expired. Re-run the login CLI."
                    )
                # Give a lazily-loaded map a moment to issue its requests.
                await page.wait_for_timeout(5000)
            finally:
                await context.close()
                await browser.close()

        if not payloads:
            raise FuelPriceUnavailable(
                "Logged in successfully but captured no station payload. Set "
                "CONTRACT_PORTAL_MAP_API_PATTERN to the fragment of the portal's "
                f"map API URL (currently {pattern!r})."
            )

        if self._dump_payloads:
            target = Path(self.settings.scraper_state_dir) / "portal_payload_sample.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payloads[:3], indent=2)[:2_000_000])
            logger.warning("wrote a sample of the captured payload to %s", target)

        return payloads

    async def _load(self) -> tuple[list[StationRecord], list[PriceRecord]]:
        if self._cache is None:
            payloads = await self._capture()
            self._cache = parse_portal_payload(payloads, self._as_of or date.today())
        return self._cache

    async def fetch_stations(self) -> list[StationRecord]:
        return (await self._load())[0]

    async def fetch_prices(self, stations: list[StationRecord]) -> list[PriceRecord]:
        return (await self._load())[1]

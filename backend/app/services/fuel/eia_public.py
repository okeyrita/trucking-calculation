"""Live regional diesel prices from EIA — the working no-2FA reference source.

Why this source and not a truck-stop site: EIA's weekly on-highway diesel table is
public-domain US government data with no login, no 2FA and no terms forbidding
automated reading, and it is a plain HTML table that needs no browser. Scraping
retail fuel sites (GasBuddy, AAA) means fighting bot protection to get numbers
that are not the company's contract prices anyway.

What it does and does not give us: the regional averages are real and refreshed
weekly, which is where most of the price difference along a route comes from. It
has no per-station detail, so the station spread still comes from
:mod:`app.services.fuel.pricing_model`. Contract prices require the portal
provider.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import httpx

from app.services.fuel.base import (
    FuelPriceProvider,
    FuelPriceUnavailable,
    PriceRecord,
    StationRecord,
)
from app.services.fuel.pricing_model import PADD_SNAPSHOT, modelled_price
from app.services.fuel.seed import load_seed_stations

logger = logging.getLogger(__name__)

EIA_URL = "https://www.eia.gov/petroleum/gasdiesel/"

# The page carries a gasoline table and a diesel table with identical markup, so
# the caption is the only reliable way to tell them apart. Picking the wrong one
# silently prices diesel as gasoline.
_DIESEL_CAPTION = re.compile(r"<caption>[^<]*Diesel[^<]*", re.IGNORECASE)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_PRICE = re.compile(r"^\d\.\d{3}$")

# Only the rows we actually use are mapped. "West Coast (PADD5)" is deliberately
# absent: it bundles California in, which would skew every other western state, so
# PADD5 is taken from the "West Coast less California" row and CA stands alone.
_LABEL_TO_REGION = {
    "new england": "PADD1A",
    "central atlantic": "PADD1B",
    "lower atlantic": "PADD1C",
    "midwest": "PADD2",
    "gulf coast": "PADD3",
    "rocky mountain": "PADD4",
    "west coast less california": "PADD5",
    "california": "CA",
}


def parse_regional_prices(html: str) -> dict[str, float]:
    """Pull ``{region: usd_per_gallon}`` out of the EIA diesel table."""
    match = _DIESEL_CAPTION.search(html)
    if not match:
        raise FuelPriceUnavailable(
            "EIA page layout changed: no table captioned 'Diesel' was found"
        )

    prices: dict[str, float] = {}
    for row_html in _ROW.findall(html[match.start() :]):
        cells = [_TAGS.sub("", cell).strip() for cell in _CELL.findall(row_html)]
        if len(cells) < 2 or not _PRICE.match(cells[1]):
            continue
        label = re.sub(r"\s*\(PADD[^)]*\)", "", cells[0]).strip().lower()
        region = _LABEL_TO_REGION.get(label)
        if region and region not in prices:
            prices[region] = float(cells[1])

    if len(prices) < 4:
        raise FuelPriceUnavailable(
            f"EIA diesel table parsed but yielded only {len(prices)} regions: {prices}"
        )
    return prices


class EiaPublicFuelPriceProvider(FuelPriceProvider):
    name = "public_eia"
    contract_prices = False

    def __init__(self, client: httpx.AsyncClient | None = None, as_of: date | None = None):
        self._client = client
        self._as_of = as_of
        self._regional: dict[str, float] | None = None

    async def _fetch_regional(self) -> dict[str, float]:
        async def get(client: httpx.AsyncClient) -> str:
            response = await client.get(
                EIA_URL,
                timeout=30.0,
                headers={"User-Agent": "trucking-fuel-routing/0.1 (+fleet fuel optimization)"},
                follow_redirects=True,
            )
            if response.status_code != 200:
                raise FuelPriceUnavailable(f"EIA returned HTTP {response.status_code}")
            return response.text

        if self._client is not None:
            html = await get(self._client)
        else:
            async with httpx.AsyncClient() as client:
                html = await get(client)

        regional = parse_regional_prices(html)
        # Fill any region the table omitted this week from the snapshot, so one
        # missing row does not knock out a whole part of the country.
        merged = {**PADD_SNAPSHOT, **regional}
        logger.info("EIA diesel prices: %s", regional)
        return merged

    async def fetch_stations(self) -> list[StationRecord]:
        # EIA publishes no station list; the geography stays the OSM export.
        return load_seed_stations()

    async def fetch_prices(self, stations: list[StationRecord]) -> list[PriceRecord]:
        if self._regional is None:
            self._regional = await self._fetch_regional()
        effective = self._as_of or date.today()
        return [
            PriceRecord(
                external_id=station.external_id,
                price_per_gallon=modelled_price(
                    station.external_id, station.state, self._regional
                ),
                effective_date=effective,
                is_contract_price=False,
            )
            for station in stations
        ]

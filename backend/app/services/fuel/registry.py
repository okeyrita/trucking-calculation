"""Provider lookup by configured name."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.services.fuel.base import FuelPriceProvider
from app.services.fuel.eia_public import EiaPublicFuelPriceProvider
from app.services.fuel.seed import SeedFuelPriceProvider


def build_fuel_provider(
    name: str | None = None,
    settings: Settings | None = None,
    storage_state: dict[str, Any] | None = None,
) -> FuelPriceProvider:
    """Instantiate the configured provider.

    ``contract_portal`` is imported lazily: it pulls in Playwright, which the API
    container has no reason to load just to serve a route request.
    """
    settings = settings or get_settings()
    name = name or settings.fuel_price_provider

    if name == "seed":
        return SeedFuelPriceProvider()
    if name == "public_eia":
        return EiaPublicFuelPriceProvider()
    if name == "contract_portal":
        from app.scrapers.providers.contract_portal import ContractPortalProvider

        return ContractPortalProvider(storage_state=storage_state, settings=settings)

    raise ValueError(f"unknown fuel price provider: {name!r}")

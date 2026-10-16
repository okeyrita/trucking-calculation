"""Pull stations and prices from a provider into the database.

Idempotent by design: stations are keyed by ``(provider, external_id)`` and prices
by ``(station, fuel type, date)``, so running the refresh twice in a day updates
rows instead of duplicating them, and a half-finished run can simply be repeated.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuelPrice, FuelStation
from app.services.fuel.base import (
    FetchReport,
    FuelPriceProvider,
    FuelPriceUnavailable,
    NeedsLogin,
    PriceRecord,
    StationRecord,
)

logger = logging.getLogger(__name__)

_CHUNK = 500


async def _upsert_stations(
    session: AsyncSession,
    provider: str,
    tenant_id: uuid.UUID,
    records: list[StationRecord],
) -> int:
    written = 0
    for start in range(0, len(records), _CHUNK):
        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "provider": provider,
                "external_id": r.external_id,
                "brand": r.brand,
                "name": r.name,
                "address": r.address,
                "city": r.city,
                "state": r.state,
                # ST_MakePoint takes longitude first.
                "geom": func.ST_SetSRID(func.ST_MakePoint(r.lon, r.lat), 4326),
                "accepts_card": r.accepts_card,
                "has_truck_lanes": r.has_truck_lanes,
            }
            for r in records[start : start + _CHUNK]
        ]
        statement = insert(FuelStation).values(rows)
        statement = statement.on_conflict_do_update(
            constraint="uq_fuel_stations_provider_external",
            set_={
                "name": statement.excluded.name,
                "brand": statement.excluded.brand,
                "address": statement.excluded.address,
                "city": statement.excluded.city,
                "state": statement.excluded.state,
                "geom": statement.excluded.geom,
                "accepts_card": statement.excluded.accepts_card,
                "has_truck_lanes": statement.excluded.has_truck_lanes,
            },
        )
        await session.execute(statement)
        written += len(rows)
    return written


async def _upsert_prices(
    session: AsyncSession,
    provider: str,
    records: list[PriceRecord],
    is_contract: bool,
) -> int:
    # Map the provider's ids onto our primary keys in one query.
    id_rows = await session.execute(
        select(FuelStation.external_id, FuelStation.id).where(FuelStation.provider == provider)
    )
    station_ids = {external: pk for external, pk in id_rows.all()}

    rows = [
        {
            "id": uuid.uuid4(),
            "station_id": station_ids[r.external_id],
            "fuel_type": r.fuel_type,
            "price_per_gallon": r.price_per_gallon,
            "is_contract_price": r.is_contract_price and is_contract,
            "effective_date": r.effective_date,
            "source": provider,
        }
        for r in records
        if r.external_id in station_ids
    ]
    skipped = len(records) - len(rows)
    if skipped:
        logger.warning("%d price rows had no matching station and were skipped", skipped)

    written = 0
    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        statement = insert(FuelPrice).values(chunk)
        statement = statement.on_conflict_do_update(
            constraint="uq_fuel_prices_station_type_date",
            set_={
                "price_per_gallon": statement.excluded.price_per_gallon,
                "is_contract_price": statement.excluded.is_contract_price,
                "source": statement.excluded.source,
            },
        )
        await session.execute(statement)
        written += len(chunk)
    return written


async def refresh_fuel_data(
    session: AsyncSession,
    provider: FuelPriceProvider,
    tenant_id: uuid.UUID,
) -> FetchReport:
    """Fetch and store everything the provider knows. Never raises for an
    expected failure — the caller gets a report it can act on."""
    report = FetchReport(provider=provider.name)

    try:
        stations = await provider.fetch_stations()
        prices = await provider.fetch_prices(stations)
    except NeedsLogin as exc:
        report.status = "needs_login"
        report.message = str(exc)
        logger.warning("fuel refresh needs a manual login: %s", exc)
        return report
    except FuelPriceUnavailable as exc:
        report.status = "error"
        report.message = str(exc)
        logger.error("fuel refresh failed: %s", exc)
        return report

    report.stations = await _upsert_stations(session, provider.name, tenant_id, stations)
    report.prices = await _upsert_prices(session, provider.name, prices, provider.contract_prices)

    if not provider.contract_prices:
        report.warnings.append(
            "Prices are retail/modelled, not the company's contract prices. "
            "Savings figures are indicative until the fuel-card portal is connected."
        )
    logger.info(
        "fuel refresh via %s: %d stations, %d prices",
        provider.name,
        report.stations,
        report.prices,
    )
    return report

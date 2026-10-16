"""Operational commands: database seeding and a one-off fuel-price refresh.

    python -m app.cli seed            # tenant, truck profiles, states, IFTA rates, stations
    python -m app.cli refresh-prices  # run the configured fuel provider once
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import DEFAULT_TENANT_ID, IftaRate, Tenant, TruckProfile, UsState
from app.services.fuel.refresh import refresh_fuel_data
from app.services.fuel.registry import build_fuel_provider
from app.services.fuel.seed import SeedFuelPriceProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
logger = logging.getLogger("seed")

SEEDS_DIR = Path(__file__).resolve().parent / "seeds"

# One default profile so the API is usable straight after a fresh start.
DEFAULT_TRUCKS = [
    {
        "name": "Class 8 sleeper (default)",
        "mpg": 6.5,
        "tank_gallons": 200.0,
        "reserve_fraction": 0.15,
    },
    {
        "name": "Class 8 day cab (thirsty)",
        "mpg": 5.8,
        "tank_gallons": 150.0,
        "reserve_fraction": 0.20,
    },
]


async def _seed_tenant(session: AsyncSession) -> uuid.UUID:
    exists = (
        await session.execute(select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID))
    ).scalar_one_or_none()
    if exists is None:
        session.add(Tenant(id=DEFAULT_TENANT_ID, name="Default carrier"))
        await session.flush()
        logger.info("created default tenant")
    return DEFAULT_TENANT_ID


async def _seed_trucks(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    created = 0
    for spec in DEFAULT_TRUCKS:
        exists = (
            await session.execute(
                select(TruckProfile).where(
                    TruckProfile.tenant_id == tenant_id, TruckProfile.name == spec["name"]
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(TruckProfile(tenant_id=tenant_id, **spec))
            created += 1
    await session.flush()
    return created


async def _seed_states(session: AsyncSession) -> int:
    path = SEEDS_DIR / "us_states.geojson"
    if not path.exists():
        logger.warning("no %s — per-state IFTA mileage will be empty", path.name)
        return 0

    existing = (await session.execute(select(func.count()).select_from(UsState))).scalar_one()
    if existing >= 50:
        return 0

    data = json.loads(path.read_text())
    rows = []
    for feature in data["features"]:
        rows.append(
            {
                "code": feature["properties"]["code"],
                "name": feature["properties"]["name"],
                "geom": func.ST_Multi(
                    func.ST_SetSRID(
                        func.ST_GeomFromGeoJSON(json.dumps(feature["geometry"])), 4326
                    )
                ),
            }
        )

    for row in rows:
        statement = insert(UsState).values(**row)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["code"],
                set_={"name": statement.excluded.name, "geom": statement.excluded.geom},
            )
        )
    await session.flush()
    return len(rows)


async def _seed_ifta(session: AsyncSession) -> int:
    path = SEEDS_DIR / "ifta_rates.csv"
    if not path.exists():
        logger.warning("no %s — the IFTA 'net' mode will treat every state as zero-tax", path.name)
        return 0

    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(line for line in handle if not line.startswith("#"))
        rows = list(reader)

    for row in rows:
        statement = insert(IftaRate).values(
            id=uuid.uuid4(),
            state_code=row["state_code"],
            fuel_type=row["fuel_type"],
            tax_per_gallon=float(row["tax_per_gallon"]),
            effective_from=date.fromisoformat(row["effective_from"]),
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_ifta_rates_state_type_from",
                set_={"tax_per_gallon": statement.excluded.tax_per_gallon},
            )
        )
    await session.flush()
    logger.warning(
        "IFTA rates are seeded placeholders — verify against https://www.iftach.org/ "
        "before using them for filing or billing"
    )
    return len(rows)


async def seed() -> int:
    async with session_scope() as session:
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        tenant_id = await _seed_tenant(session)
        trucks = await _seed_trucks(session, tenant_id)
        states = await _seed_states(session)
        rates = await _seed_ifta(session)

        # Stations always come from the bundled export: it is the offline baseline
        # every provider builds on, and re-running it is a cheap no-op.
        report = await refresh_fuel_data(session, SeedFuelPriceProvider(), tenant_id)
        await session.commit()

    logger.info(
        "seed done: %d truck profiles, %d states, %d IFTA rates, %d stations, %d prices",
        trucks,
        states,
        rates,
        report.stations,
        report.prices,
    )
    return 0


async def refresh_prices(provider_name: str | None) -> int:
    settings = get_settings()
    name = provider_name or settings.fuel_price_provider
    async with session_scope() as session:
        storage_state = None
        if name == "contract_portal":
            from app.scrapers.session import ScraperSessionStore

            storage_state = await ScraperSessionStore(session).load_storage_state(name)

        provider = build_fuel_provider(name, settings, storage_state)
        report = await refresh_fuel_data(session, provider, DEFAULT_TENANT_ID)
        await session.commit()

    logger.info("provider=%s status=%s prices=%d", report.provider, report.status, report.prices)
    if report.message:
        logger.warning(report.message)
    for warning in report.warnings:
        logger.warning(warning)
    return 0 if report.status == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="load tenant, trucks, states, IFTA rates and stations")
    refresh = sub.add_parser("refresh-prices", help="run a fuel-price provider once")
    refresh.add_argument("--provider", default=None, help="seed | public_eia | contract_portal")

    args = parser.parse_args()
    if args.command == "seed":
        return asyncio.run(seed())
    if args.command == "refresh-prices":
        return asyncio.run(refresh_prices(args.provider))
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

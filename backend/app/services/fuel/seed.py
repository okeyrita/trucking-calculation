"""Offline fuel-price provider: real stations, snapshot regional prices.

The station list is real OpenStreetMap data (see ``app/seeds/stations.csv``), so
the geography the optimizer works on — where truck stops actually sit relative to
the interstates — is genuine. Prices come from the embedded EIA snapshot plus the
per-station model, which makes this provider fully offline and deterministic: it is
what the test suite and a fresh ``docker compose up`` run on.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.services.fuel.base import FuelPriceProvider, PriceRecord, StationRecord
from app.services.fuel.pricing_model import modelled_price

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
STATIONS_CSV = SEEDS_DIR / "stations.csv"


def load_seed_stations(path: Path | None = None) -> list[StationRecord]:
    """Read the bundled OSM station export.

    ``accepts_card`` is modelled: the major nationwide truck-stop networks are
    assumed to honour the company's card, and independents are not. The real list
    comes from the fuel-card portal — this is a stand-in, not a fact.
    """
    csv_path = path or STATIONS_CSV
    records: list[StationRecord] = []

    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            in_network = row.get("truck_network") == "yes"
            records.append(
                StationRecord(
                    external_id=row["external_id"],
                    name=row["name"],
                    state=row["state"],
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    brand=row.get("brand") or None,
                    address=row.get("address") or None,
                    city=row.get("city") or None,
                    accepts_card=in_network,
                    has_truck_lanes=in_network or row.get("hgv_tagged") == "yes",
                )
            )
    return records


class SeedFuelPriceProvider(FuelPriceProvider):
    name = "seed"
    contract_prices = False

    def __init__(self, stations_csv: Path | None = None, as_of: date | None = None):
        self._csv = stations_csv
        self._as_of = as_of

    async def fetch_stations(self) -> list[StationRecord]:
        return load_seed_stations(self._csv)

    async def fetch_prices(self, stations: list[StationRecord]) -> list[PriceRecord]:
        effective = self._as_of or date.today()
        return [
            PriceRecord(
                external_id=station.external_id,
                price_per_gallon=modelled_price(station.external_id, station.state),
                effective_date=effective,
                is_contract_price=False,
            )
            for station in stations
        ]

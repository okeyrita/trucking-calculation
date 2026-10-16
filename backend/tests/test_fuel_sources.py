"""Fuel-price source tests: the EIA parser, the price model, and the seed export."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.services.fuel.base import FuelPriceUnavailable
from app.services.fuel.eia_public import EiaPublicFuelPriceProvider, parse_regional_prices
from app.services.fuel.pricing_model import (
    PADD_SNAPSHOT,
    STATE_TO_REGION,
    modelled_price,
    region_for_state,
    station_offset,
)
from app.services.fuel.seed import SeedFuelPriceProvider, load_seed_stations
from tests.conftest import mock_client


class TestEiaParser:
    def test_picks_the_diesel_table_not_the_gasoline_one(self, eia_html):
        prices = parse_regional_prices(eia_html)

        # The fixture holds both tables; gasoline is around $4, diesel around $5.6.
        assert prices["PADD3"] > 5.0, "parsed the gasoline table by mistake"
        expected = {"PADD1A", "PADD1B", "PADD1C", "PADD2", "PADD3", "PADD4", "PADD5", "CA"}
        assert set(prices) >= expected

    def test_california_is_kept_separate_from_the_west_coast(self, eia_html):
        prices = parse_regional_prices(eia_html)

        # PADD5 must come from "West Coast less California"; otherwise California's
        # outlier price would be smeared across every western state.
        assert prices["CA"] > prices["PADD5"]
        assert prices["CA"] - prices["PADD3"] > 1.0

    def test_a_layout_change_fails_loudly(self):
        with pytest.raises(FuelPriceUnavailable, match="layout changed"):
            parse_regional_prices("<html><body><p>nothing here</p></body></html>")

    def test_a_diesel_table_with_no_rows_fails(self):
        with pytest.raises(FuelPriceUnavailable, match="only"):
            parse_regional_prices("<table><caption>Diesel Fuel Prices</caption></table>")

    async def test_http_error_is_wrapped(self):
        provider = EiaPublicFuelPriceProvider(
            mock_client(lambda r: httpx.Response(503, text="down"))
        )
        with pytest.raises(FuelPriceUnavailable, match="HTTP 503"):
            await provider.fetch_prices([])

    async def test_live_fetch_prices_stations_by_region(self, eia_html):
        provider = EiaPublicFuelPriceProvider(
            mock_client(lambda r: httpx.Response(200, text=eia_html)), as_of=date(2026, 1, 15)
        )
        stations = [s for s in load_seed_stations() if s.state in ("TX", "CA")][:40]
        prices = await provider.fetch_prices(stations)

        by_id = {p.external_id: p for p in prices}
        tx = [by_id[s.external_id].price_per_gallon for s in stations if s.state == "TX"]
        ca = [by_id[s.external_id].price_per_gallon for s in stations if s.state == "CA"]
        if tx and ca:
            assert min(ca) > max(tx), "California must price above the Gulf Coast"
        assert all(p.effective_date == date(2026, 1, 15) for p in prices)
        # Never claim retail/modelled numbers are the company's contract prices.
        assert all(p.is_contract_price is False for p in prices)


class TestPricingModel:
    def test_every_state_maps_to_a_region(self):
        stations = load_seed_stations()
        unmapped = {s.state for s in stations} - set(STATE_TO_REGION)
        assert unmapped == set(), f"unmapped states in the seed data: {unmapped}"

    def test_offsets_are_deterministic_and_bounded(self):
        assert station_offset("osm:w1") == station_offset("osm:w1")
        assert station_offset("osm:w1") != station_offset("osm:w2")
        offsets = [station_offset(f"osm:w{i}") for i in range(500)]
        assert all(-0.15 <= o <= 0.15 for o in offsets)

    def test_regional_differences_survive_the_station_spread(self):
        """The point of the product: crossing a state line must still be worth it.

        The per-station spread is +/-$0.15, so it must never be large enough to
        swamp a real regional gap like Gulf Coast vs California.
        """
        gulf = regional = PADD_SNAPSHOT["PADD3"]
        california = PADD_SNAPSHOT["CA"]
        worst_gulf = gulf + 0.15
        best_california = california - 0.15
        assert worst_gulf < best_california
        assert regional == gulf  # sanity: snapshot lookup did not mutate

    def test_unknown_state_falls_back_instead_of_raising(self):
        assert region_for_state("ZZ") == "PADD2"
        assert modelled_price("osm:w1", "ZZ") > 0


class TestSeedProvider:
    def test_station_export_is_usable(self):
        stations = load_seed_stations()

        assert len(stations) > 1000, "the bundled OSM export looks truncated"
        assert all(-125 < s.lon < -66 for s in stations), "a station sits outside the US"
        assert all(24 < s.lat < 50 for s in stations)
        assert all(len(s.state) == 2 for s in stations)
        # Card acceptance is modelled from the major networks; it must not be all-or-nothing.
        accepting = [s for s in stations if s.accepts_card]
        assert 0 < len(accepting) < len(stations)

    async def test_prices_cover_every_station_exactly_once(self):
        provider = SeedFuelPriceProvider(as_of=date(2026, 3, 1))
        stations = await provider.fetch_stations()
        prices = await provider.fetch_prices(stations)

        assert len(prices) == len(stations)
        assert len({p.external_id for p in prices}) == len(prices)
        assert all(1.0 < p.price_per_gallon < 12.0 for p in prices)

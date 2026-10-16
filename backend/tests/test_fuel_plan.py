"""Unit tests for the fuel-plan core.

All synthetic: stations are placed at round mile markers with hand-picked prices so
the optimal answer can be computed by hand and asserted exactly.
"""

import functools

import pytest

from app.services.optimizer.fuel_plan import (
    FuelPlanError,
    StationCandidate,
    TruckSpec,
    baseline_fuel_plan,
    compare_plans,
    optimize_fuel_plan,
    shift_stations_to_position,
)

# 100 usable gallons (200 - 15% reserve = 170) ... keep the numbers round instead:
# tank 100, no reserve, 10 mpg => 1000 mi of range, 1 gallon per 10 miles.
ROUND_TRUCK = TruckSpec(mpg=10.0, tank_gallons=100.0, reserve_fraction=0.0)

# Realistic Class 8: 200 gal tank, 6.5 mpg, 15% reserve => 170 usable, 1105 mi range.
CLASS8 = TruckSpec(mpg=6.5, tank_gallons=200.0, reserve_fraction=0.15)


def station(mile, price, name=None, tax=0.0, state="TX"):  # noqa: D103
    return StationCandidate(
        station_id=f"s{mile:.0f}",
        name=name or f"Stop@{mile:.0f}",
        state=state,
        mile_marker=float(mile),
        price_per_gallon=float(price),
        tax_per_gallon=float(tax),
    )


def gallons_at(plan, mile):
    return next((s.gallons for s in plan.stops if s.mile_marker == mile), 0.0)


class TestTruckSpec:
    def test_mpg_is_inverse_of_consumption(self):
        """gallons = miles / mpg — the US convention, not miles * mpg."""
        assert CLASS8.gallons_for(650.0) == pytest.approx(100.0)
        assert CLASS8.miles_for(100.0) == pytest.approx(650.0)

    def test_reserve_shrinks_usable_range(self):
        assert CLASS8.usable_gallons == pytest.approx(170.0)
        assert CLASS8.range_miles == pytest.approx(1105.0)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"mpg": 0, "tank_gallons": 100},
            {"mpg": 6.5, "tank_gallons": -1},
            {"mpg": 6.5, "tank_gallons": 100, "reserve_fraction": 1.0},
        ],
    )
    def test_rejects_impossible_specs(self, kwargs):
        with pytest.raises(FuelPlanError):
            TruckSpec(**kwargs)


class TestOptimizerDecisions:
    def test_buys_minimum_to_reach_a_cheaper_station(self):
        """Expensive now, cheap in 200 mi: buy exactly the 20 gal to get there."""
        stations = [station(0, 5.00), station(200, 3.00)]
        plan = optimize_fuel_plan(1000, stations, ROUND_TRUCK, start_fuel_gallons=0)

        assert gallons_at(plan, 0) == pytest.approx(20.0)
        # 1000 mi trip needs 100 gal total; the rest is bought at the cheap stop.
        assert gallons_at(plan, 200) == pytest.approx(80.0)
        assert plan.total_cost == pytest.approx(20 * 5.00 + 80 * 3.00)

    def test_fills_up_when_nothing_cheaper_is_in_range(self):
        """Cheap now, expensive later, and the trip is longer than one tank:
        leave the cheap station full and buy only the shortfall later."""
        stations = [station(0, 3.00), station(200, 5.00)]
        plan = optimize_fuel_plan(1100, stations, ROUND_TRUCK, start_fuel_gallons=0)

        assert gallons_at(plan, 0) == pytest.approx(100.0)  # full tank
        # 1100 mi needs 110 gal; the 10 gal shortfall is topped up at the pricey stop.
        assert gallons_at(plan, 200) == pytest.approx(10.0)

    def test_buys_everything_at_the_cheapest_stop_when_one_tank_is_enough(self):
        """Range 1000 mi covers the whole 1000 mi trip, so the expensive stop at
        mile 200 is never touched."""
        stations = [station(0, 3.00), station(200, 5.00)]
        plan = optimize_fuel_plan(1000, stations, ROUND_TRUCK, start_fuel_gallons=0)

        assert gallons_at(plan, 0) == pytest.approx(100.0)
        assert gallons_at(plan, 200) == 0.0

    def test_skips_a_station_that_is_never_worth_using(self):
        stations = [station(0, 3.00), station(100, 9.99), station(500, 3.10)]
        plan = optimize_fuel_plan(1400, stations, ROUND_TRUCK, start_fuel_gallons=0)

        assert gallons_at(plan, 100) == 0.0
        assert [s.mile_marker for s in plan.stops] == [0.0, 500.0]

    def test_never_exceeds_tank_capacity(self):
        stations = [station(m, 4.00 - m / 10000) for m in range(0, 2000, 150)]
        plan = optimize_fuel_plan(2000, stations, CLASS8, start_fuel_gallons=50)

        for stop in plan.stops:
            assert stop.departure_gallons <= CLASS8.tank_gallons + 1e-6

    def test_never_dips_below_the_reserve(self):
        stations = [station(m, 4.00) for m in range(0, 2000, 400)]
        plan = optimize_fuel_plan(2000, stations, CLASS8, start_fuel_gallons=200)

        for stop in plan.stops:
            assert stop.arrival_gallons >= CLASS8.reserve_gallons - 1e-6
        assert plan.arrival_gallons >= CLASS8.reserve_gallons - 1e-6

    def test_buys_nothing_when_the_tank_already_covers_the_trip(self):
        stations = [station(100, 3.00)]
        plan = optimize_fuel_plan(300, stations, ROUND_TRUCK, start_fuel_gallons=100)

        assert plan.stops == []
        assert plan.total_cost == 0.0
        assert plan.arrival_gallons == pytest.approx(70.0)

    def test_total_gallons_match_the_distance_burnt(self):
        stations = [station(m, 4.00 + (m % 300) / 100) for m in range(0, 1500, 100)]
        plan = optimize_fuel_plan(1500, stations, CLASS8, start_fuel_gallons=100)

        burnt = CLASS8.gallons_for(1500)
        on_board_change = plan.arrival_gallons - 100.0
        assert plan.total_gallons == pytest.approx(burnt + on_board_change, abs=1e-6)


class TestOptimality:
    """Cross-check the greedy against an exact dynamic program.

    The DP is only tractable on a grid, so distances are multiples of 50 mi with
    mpg 10 — one grid unit is 5 gallons. Every amount the greedy can buy (a full
    tank, or exactly enough to reach another station) is a whole number of units on
    that grid, so the two methods are comparing the same feasible set.
    """

    UNIT_MILES = 50
    UNIT_GALLONS = 5.0
    TANK_UNITS = 6  # 30 gal tank => 300 mi range

    def _exact_min_cost(self, marks, prices, total):
        """Exact minimum cost by DP over (station, fuel units on arrival)."""

        positions = [m // self.UNIT_MILES for m in marks]
        dest = total // self.UNIT_MILES

        @functools.cache
        def best(i, fuel):
            gap = (positions[i + 1] if i + 1 < len(positions) else dest) - positions[i]
            out = float("inf")
            for buy in range(0, self.TANK_UNITS - fuel + 1):
                after = fuel + buy
                if after < gap:
                    continue
                spend = buy * self.UNIT_GALLONS * prices[i]
                rest = 0.0 if i + 1 >= len(positions) else best(i + 1, after - gap)
                out = min(out, spend + rest)
            return out

        return best(0, 0)

    def test_matches_exact_dynamic_program(self):
        import random

        rng = random.Random(1234)
        truck = TruckSpec(
            mpg=10.0, tank_gallons=self.TANK_UNITS * self.UNIT_GALLONS, reserve_fraction=0.0
        )
        checked = 0

        for _ in range(80):
            # Station at mile 0 and a start-empty tank, so the DP and the greedy
            # begin from the same state.
            marks = [0] + sorted(rng.sample(range(50, 500, self.UNIT_MILES), 5))
            prices = [round(rng.uniform(2.5, 5.0), 2) for _ in marks]
            total = marks[-1] + rng.choice([50, 100, 150])

            stations = [station(m, p) for m, p in zip(marks, prices, strict=True)]
            got = optimize_fuel_plan(
                total, stations, truck, start_fuel_gallons=0, stop_overhead_usd=0
            )
            expected = self._exact_min_cost(marks, prices, total)
            if not got.feasible or expected == float("inf"):
                continue

            checked += 1
            assert got.total_cost == pytest.approx(expected, abs=1e-6), (
                f"greedy {got.total_cost} vs exact {expected} "
                f"for {list(zip(marks, prices, strict=True))} "
                f"to mile {total}"
            )

        assert checked > 40, f"only {checked} instances were feasible; the test is not exercising"


class TestClusterCollapse:
    def test_keeps_only_the_cheapest_of_a_cluster(self):
        from app.services.optimizer.fuel_plan import _collapse_clusters

        stations = [
            station(100.0, 5.90, name="a"),
            station(100.8, 5.40, name="b"),  # same interchange as a
            station(101.5, 5.70, name="c"),  # still within 2 mi of a
            station(400.0, 5.60, name="d"),  # a genuinely separate stop
        ]
        kept = [s.name for s in _collapse_clusters(stations, "pump")]

        assert kept == ["b", "d"]

    def test_clusters_are_judged_on_the_chosen_basis(self):
        """On the net basis a different member of the cluster can be the cheap one,
        because the states either side of a border tax fuel differently."""
        from app.services.optimizer.fuel_plan import _collapse_clusters

        stations = [
            station(100.0, 5.50, name="low-tax", tax=0.20, state="TX"),
            station(101.0, 5.60, name="high-tax", tax=0.60, state="IL"),
        ]

        assert [s.name for s in _collapse_clusters(stations, "pump")] == ["low-tax"]
        assert [s.name for s in _collapse_clusters(stations, "net")] == ["high-tax"]

    def test_widely_spaced_stations_are_untouched(self):
        from app.services.optimizer.fuel_plan import _collapse_clusters

        stations = [station(m, 5.0 + m / 1000) for m in (0, 100, 200, 300)]

        assert len(_collapse_clusters(stations, "pump")) == 4


class TestIftaBasis:
    def test_net_basis_can_pick_a_different_station(self):
        """A higher pump price in a high-tax state can be the cheaper real cost.

        TX pump 4.00 with 0.20 tax => 3.80 net.
        PA pump 4.10 with 0.75 tax => 3.35 net, i.e. cheaper for the company.
        Optimizing on the pump price picks TX and leaves money on the table.
        """
        stations = [
            station(0, 4.00, name="TX stop", tax=0.20, state="TX"),
            station(50, 4.10, name="PA stop", tax=0.75, state="PA"),
        ]
        pump = optimize_fuel_plan(600, stations, ROUND_TRUCK, 0, basis="pump")
        net = optimize_fuel_plan(600, stations, ROUND_TRUCK, 0, basis="net")

        # On the pump basis TX looks cheapest, so it fills up there.
        assert gallons_at(pump, 0) > gallons_at(pump, 50)
        # On the net basis the PA stop wins: buy only enough at TX to reach it.
        assert gallons_at(net, 0) == pytest.approx(5.0)
        assert gallons_at(net, 50) == pytest.approx(55.0)
        # And the net plan really is cheaper once the tax credit is counted.
        assert net.total_net_cost < pump.total_net_cost

    def test_both_totals_are_always_reported(self):
        stations = [station(0, 4.00, tax=0.25)]
        plan = optimize_fuel_plan(500, stations, ROUND_TRUCK, 0)

        assert plan.total_cost == pytest.approx(50 * 4.00)
        assert plan.total_net_cost == pytest.approx(50 * 3.75)


class TestFeasibility:
    def test_reports_the_gap_that_breaks_the_trip(self):
        stations = [station(0, 4.00), station(900, 4.00)]  # 900 mi gap, 300 mi range
        truck = TruckSpec(mpg=10.0, tank_gallons=30.0, reserve_fraction=0.0)
        plan = optimize_fuel_plan(1000, stations, truck, start_fuel_gallons=30)

        assert not plan.feasible
        assert "900 mi gap" in plan.infeasible_reason
        assert plan.stops == []

    def test_reports_an_unreachable_first_station(self):
        plan = optimize_fuel_plan(1000, [station(500, 4.00)], ROUND_TRUCK, start_fuel_gallons=10)

        assert not plan.feasible
        assert "on board at departure" in plan.infeasible_reason

    def test_reports_no_stations_at_all(self):
        plan = optimize_fuel_plan(1000, [], ROUND_TRUCK, start_fuel_gallons=10)

        assert not plan.feasible
        assert "No card-accepting station" in plan.infeasible_reason

    def test_no_stations_needed_is_still_feasible(self):
        plan = optimize_fuel_plan(100, [], ROUND_TRUCK, start_fuel_gallons=50)

        assert plan.feasible
        assert plan.stops == []

    def test_rejects_a_start_level_above_the_tank(self):
        with pytest.raises(FuelPlanError):
            optimize_fuel_plan(100, [], ROUND_TRUCK, start_fuel_gallons=500)


class TestBaselineAndSavings:
    def test_baseline_ignores_price_and_costs_more(self):
        """The naive driver rolls to the last station they can reach and fills up
        there — which here is the most expensive one on the route."""
        stations = [station(0, 3.00), station(150, 6.00)]
        truck = TruckSpec(mpg=10.0, tank_gallons=30.0, reserve_fraction=0.0)  # 300 mi

        # Leaves home with 200 mi of fuel on board, so the gauge lets the driver
        # roll straight past the cheap stop at mile 0.
        cmp = compare_plans(400, stations, truck, start_fuel_gallons=20, basis="pump")

        assert cmp.baseline.stops[0].mile_marker == 150.0  # drove past the cheap stop
        assert cmp.optimized.stops[0].mile_marker == 0.0
        assert cmp.savings_usd > 0
        assert 0 < cmp.savings_pct < 100

    def test_both_plans_buy_the_same_gallons(self):
        """The savings figure is only honest if both plans price identical fuel.

        A baseline that ends the trip with a tank full of unburned fuel "costs"
        more merely for having bought more, which would turn the headline number
        into fiction. Both plans must purchase exactly what the trip burns.
        """
        stations = [station(m, 4.00 + (m % 400) / 500) for m in range(0, 2000, 200)]
        cmp = compare_plans(2000, stations, CLASS8, start_fuel_gallons=60)

        assert cmp.optimized.total_gallons == pytest.approx(cmp.baseline.total_gallons, abs=1e-6)
        assert cmp.optimized.arrival_gallons == pytest.approx(
            cmp.baseline.arrival_gallons, abs=1e-6
        )

    def test_identical_prices_mean_zero_savings(self):
        """With one price everywhere there is no decision to get right, so the
        product must claim no credit."""
        stations = [station(m, 5.50) for m in range(100, 2000, 300)]
        cmp = compare_plans(2000, stations, CLASS8, start_fuel_gallons=60)

        assert cmp.savings_usd == pytest.approx(0.0, abs=1e-6)
        assert cmp.savings_pct == pytest.approx(0.0, abs=1e-6)

    def test_savings_cannot_exceed_the_price_spread(self):
        """Sanity bound: buying the same gallons, the most that station choice can
        save is the spread between the cheapest and dearest usable price."""
        import random

        rng = random.Random(99)
        for _ in range(100):
            marks = sorted(rng.sample(range(0, 2400, 50), 10))
            prices = [round(rng.uniform(4.0, 6.0), 3) for _ in marks]
            stations = [station(m, p) for m, p in zip(marks, prices, strict=True)]
            total = marks[-1] + 150
            cmp = compare_plans(total, stations, CLASS8, start_fuel_gallons=rng.uniform(0, 200))
            if not cmp.optimized.feasible:
                continue

            spread = max(prices) - min(prices)
            max_possible = cmp.optimized.total_gallons * spread
            assert cmp.savings_usd <= max_possible + 1e-6

    def test_optimized_is_never_worse_than_baseline(self):
        import random

        rng = random.Random(7)
        for _ in range(200):
            marks = sorted(rng.sample(range(0, 2400, 50), 12))
            stations = [station(m, round(rng.uniform(3.0, 6.0), 3)) for m in marks]
            total = marks[-1] + 200
            cmp = compare_plans(
                total,
                stations,
                CLASS8,
                start_fuel_gallons=rng.uniform(0, 200),
                stop_overhead_usd=0,
            )
            if cmp.optimized.feasible:
                assert cmp.savings_usd >= -1e-6

    def test_stop_overhead_never_gives_up_more_than_a_stop_is_worth(self):
        """Dropping a stop is allowed to cost money — but only less than the stop
        itself costs in driver time, and only for stops actually dropped."""
        import random

        rng = random.Random(11)
        overhead = 8.0
        for _ in range(150):
            marks = sorted(rng.sample(range(0, 2400, 50), 12))
            stations = [station(m, round(rng.uniform(3.0, 6.0), 3)) for m in marks]
            total = marks[-1] + 200
            start = rng.uniform(0, 200)

            pure = optimize_fuel_plan(total, stations, CLASS8, start, stop_overhead_usd=0)
            practical = optimize_fuel_plan(
                total, stations, CLASS8, start, stop_overhead_usd=overhead
            )
            if not pure.feasible:
                continue

            # Money may only be given up in proportion to the stops actually saved.
            dropped = pure.stop_count - practical.stop_count
            penalty = practical.cost_on("pump") - pure.cost_on("pump")
            assert dropped >= 0
            assert penalty <= overhead * max(dropped, 0) + 1e-6

    def test_never_stops_twice_in_one_interchange(self):
        """The case real data threw up on a Dallas->Chicago run.

        Two truck stops a mile apart at slightly different prices made the optimum
        buy 0.1 gallons at the dearer one purely to reach the cheaper: right to the
        cent, and something no driver would ever do. Only the cheaper pump of such a
        pair is worth considering, so the plan should use it and ignore its neighbour
        — with the driver's time priced at zero as well, because this is not a
        trade-off, it is just a better answer.
        """
        stations = [
            station(0, 5.80, name="start"),
            station(600, 5.601, name="Pilot"),
            station(601, 5.490, name="Love's"),
        ]
        plan = optimize_fuel_plan(900, stations, CLASS8, 0.0, stop_overhead_usd=0)

        assert all(stop.gallons >= 1 for stop in plan.stops), "no token purchases"
        used = {stop.station.name for stop in plan.stops}
        assert "Love's" in used and "Pilot" not in used, "the cheaper pump of the pair wins"

    def test_a_load_bearing_stop_is_never_dropped(self):
        """A stop the trip cannot be completed without stays, whatever it costs."""
        # 900 mi apart with 1105 mi of range: the middle stop is the only way across.
        stations = [station(0, 4.00), station(900, 9.99), station(1800, 4.00)]
        plan = optimize_fuel_plan(2000, stations, CLASS8, start_fuel_gallons=0)

        assert plan.feasible
        assert any(s.mile_marker == 900.0 for s in plan.stops)

    def test_baseline_respects_the_same_tank_limits(self):
        stations = [station(m, 4.00) for m in range(0, 2000, 300)]
        plan = baseline_fuel_plan(2000, stations, CLASS8, start_fuel_gallons=100)

        for stop in plan.stops:
            assert stop.arrival_gallons >= CLASS8.reserve_gallons - 1e-6
            assert stop.departure_gallons <= CLASS8.tank_gallons + 1e-6


class TestReroute:
    def test_drops_passed_stations_and_rebases_the_rest(self):
        stations = [station(100, 4.00), station(400, 3.50), station(900, 3.90)]
        shifted = shift_stations_to_position(stations, consumed_miles=400)

        assert [s.mile_marker for s in shifted] == [0.0, 500.0]
        assert shifted[0].station_id == "s400"  # identity survives the shift

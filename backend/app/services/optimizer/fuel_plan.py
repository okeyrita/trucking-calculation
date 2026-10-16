"""Fuel-stop optimization — the core of the product.

Pure functions over plain dataclasses: no ORM, no I/O, no database. Everything the
algorithm needs (distances along the route, prices, tax rates) is resolved by the
caller, which keeps this module exhaustively unit-testable.

Units are US customary throughout, because that is what the domain uses:

* distance        — miles
* volume          — gallons
* fuel economy    — MPG (miles per gallon). Note this is the *inverse* of the
                    L/100km convention: ``gallons = miles / mpg``.
* money           — USD, and USD per gallon.

The optimization is the classic "gas station problem": with a fixed tank and a
known price at every station along the way, buy fuel so the trip costs the least.
The greedy rule implemented in :func:`optimize_fuel_plan` is provably optimal when
fuel can be bought in arbitrary amounts:

    At each station, if a strictly cheaper station is within tank range, buy just
    enough to reach it. Otherwise fill the tank, because everything in range is
    more expensive than here.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

CostBasis = Literal["pump", "net"]

# Distances closer than this are treated as the same point, which keeps float
# noise in the route geometry from producing zero-gallon phantom stops.
_EPSILON_MILES = 1e-6
_EPSILON_GALLONS = 1e-6

#: What pulling into a truck stop costs beyond the fuel: roughly fifteen minutes of
#: driver time plus the detour and manoeuvring. A stop that saves less than this is
#: not worth making, however correct it looks on a spreadsheet.
DEFAULT_STOP_OVERHEAD_USD = 8.0

#: Removing one stop changes what the others should buy, which can make another stop
#: not worth it; this bounds how many times we go round.
_MAX_REFINEMENTS = 8

#: A purchase this small is a rounding artefact of the optimum, not a fuel stop.
#: It is a candidate for removal; whether removing it is actually worth it is
#: decided by the cost guard, not by this number.
_TOKEN_PURCHASE_GALLONS = 20.0

#: Stations closer together than this are one stop as far as a driver is concerned —
#: a single interchange with a row of truck stops on it. Only the cheapest of them
#: can ever be worth using.
_CLUSTER_MILES = 2.0


class FuelPlanError(ValueError):
    """Raised when the inputs cannot describe a trip at all (bad truck spec etc.)."""


@dataclass(frozen=True)
class TruckSpec:
    """The "virtual tank": every Class 8 truck in the fleet is close enough to
    identical that one model per truck profile is sufficient."""

    mpg: float
    tank_gallons: float
    reserve_fraction: float = 0.15

    def __post_init__(self) -> None:
        if self.mpg <= 0:
            raise FuelPlanError("mpg must be positive")
        if self.tank_gallons <= 0:
            raise FuelPlanError("tank_gallons must be positive")
        if not 0.0 <= self.reserve_fraction < 1.0:
            raise FuelPlanError("reserve_fraction must be in [0, 1)")

    @property
    def reserve_gallons(self) -> float:
        return self.tank_gallons * self.reserve_fraction

    @property
    def usable_gallons(self) -> float:
        """Tank capacity above the safety reserve — the amount the plan may spend."""
        return self.tank_gallons - self.reserve_gallons

    @property
    def range_miles(self) -> float:
        return self.usable_gallons * self.mpg

    def gallons_for(self, miles: float) -> float:
        return miles / self.mpg

    def miles_for(self, gallons: float) -> float:
        return gallons * self.mpg


@dataclass(frozen=True)
class StationCandidate:
    """A card-accepting station, already projected onto the route.

    ``mile_marker`` is the distance from the origin along the driven route, not a
    straight line. ``detour_miles`` is the extra driving to get off the highway and
    back on; it is reported to the driver but deliberately left out of the fuel
    math, since the corridor is only a few miles wide.
    """

    station_id: str
    name: str
    state: str
    mile_marker: float
    price_per_gallon: float
    tax_per_gallon: float = 0.0
    detour_miles: float = 0.0
    lat: float | None = None
    lon: float | None = None

    @property
    def net_price_per_gallon(self) -> float:
        """Price after the IFTA credit for the state's fuel tax.

        This is what a gallon really costs the company, and it can reorder the
        stations: a high-tax state with a low pump price may beat a low-tax state.
        """
        return self.price_per_gallon - self.tax_per_gallon

    def price(self, basis: CostBasis) -> float:
        return self.price_per_gallon if basis == "pump" else self.net_price_per_gallon


@dataclass(frozen=True)
class FuelStop:
    """One recommended purchase."""

    seq: int
    station: StationCandidate
    gallons: float
    arrival_gallons: float
    departure_gallons: float
    cost: float
    net_cost: float

    @property
    def mile_marker(self) -> float:
        return self.station.mile_marker


@dataclass(frozen=True)
class FuelPlan:
    total_miles: float
    stops: list[FuelStop] = field(default_factory=list)
    total_gallons: float = 0.0
    total_cost: float = 0.0
    total_net_cost: float = 0.0
    arrival_gallons: float = 0.0
    feasible: bool = True
    infeasible_reason: str | None = None

    @property
    def stop_count(self) -> int:
        return len(self.stops)

    def cost_on(self, basis: CostBasis) -> float:
        return self.total_cost if basis == "pump" else self.total_net_cost


@dataclass(frozen=True)
class PlanComparison:
    """The optimized plan next to what an unprompted driver would have spent.

    ``savings_usd`` is measured on the same cost basis the plan optimized for, so
    the figure the customer sees is the one the algorithm actually improved.
    """

    optimized: FuelPlan
    baseline: FuelPlan
    basis: CostBasis
    savings_usd: float
    savings_pct: float


def _collapse_clusters(
    stations: list[StationCandidate], basis: CostBasis, cluster_miles: float = _CLUSTER_MILES
) -> list[StationCandidate]:
    """Keep only the cheapest station in each tight cluster.

    Busy interchanges carry several truck stops within a mile of each other. To the
    optimizer those are distinct stations at slightly different prices, so it will
    cheerfully buy a tenth of a gallon at one in order to reach the one next door —
    an answer that is right to the cent and absurd on the ground. No driver would
    ever prefer the dearer of two pumps a mile apart, so the rest are dropped before
    solving rather than patched up afterwards.
    """
    if not stations:
        return []

    collapsed: list[StationCandidate] = []
    cluster: list[StationCandidate] = [stations[0]]

    def flush() -> None:
        collapsed.append(min(cluster, key=lambda s: (s.price(basis), s.detour_miles)))

    for station in stations[1:]:
        if station.mile_marker - cluster[0].mile_marker <= cluster_miles:
            cluster.append(station)
        else:
            flush()
            cluster = [station]
    flush()
    return collapsed


def _prepare(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_fuel_gallons: float,
) -> tuple[list[StationCandidate], float]:
    """Validate inputs, drop unusable stations, and convert the starting tank
    level into "usable" gallons measured above the reserve."""
    if total_miles < 0:
        raise FuelPlanError("total_miles must not be negative")
    if start_fuel_gallons < 0:
        raise FuelPlanError("start_fuel_gallons must not be negative")
    if start_fuel_gallons > truck.tank_gallons + _EPSILON_GALLONS:
        raise FuelPlanError("start_fuel_gallons exceeds tank capacity")

    usable = [
        s
        for s in stations
        if -_EPSILON_MILES <= s.mile_marker <= total_miles + _EPSILON_MILES
        and s.price_per_gallon > 0
    ]
    usable.sort(key=lambda s: s.mile_marker)

    # Fuel is tracked above the reserve line, so 0 means "at the reserve", not "empty".
    start_usable = max(0.0, min(start_fuel_gallons, truck.tank_gallons) - truck.reserve_gallons)
    return usable, start_usable


def _check_feasible(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_usable: float,
) -> str | None:
    """Return a human-readable reason if no plan can exist, else None.

    Stopping is free in this model, so a trip is possible exactly when every gap
    between consecutive stations fits in a tank — and the first gap fits in the
    fuel already on board.
    """
    start_range = truck.miles_for(start_usable)
    if not stations:
        if total_miles > start_range + _EPSILON_MILES:
            return (
                f"No card-accepting station found along the route, and the destination is "
                f"{total_miles:.0f} mi away with only {start_range:.0f} mi of range on board."
            )
        return None

    first_gap = stations[0].mile_marker
    if first_gap > start_range + _EPSILON_MILES:
        return (
            f"First station is {first_gap:.0f} mi out but only {start_range:.0f} mi of range "
            f"is on board at departure."
        )

    for prev, nxt in zip(stations, stations[1:], strict=False):  # consecutive pairs
        gap = nxt.mile_marker - prev.mile_marker
        if gap > truck.range_miles + _EPSILON_MILES:
            return (
                f"{gap:.0f} mi gap between stations near mile {prev.mile_marker:.0f} "
                f"({prev.name}) and mile {nxt.mile_marker:.0f} ({nxt.name}) exceeds the "
                f"{truck.range_miles:.0f} mi usable range."
            )

    tail = total_miles - stations[-1].mile_marker
    if tail > truck.range_miles + _EPSILON_MILES:
        return (
            f"Last station is {tail:.0f} mi short of the destination, beyond the "
            f"{truck.range_miles:.0f} mi usable range."
        )
    return None


def _build_plan(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_usable: float,
    purchases: list[tuple[int, float]],
) -> FuelPlan:
    """Replay a list of (station index, gallons) purchases into a costed plan.

    Replaying rather than accumulating during the decision loop keeps the fuel
    bookkeeping in exactly one place, so the optimized and baseline plans cannot
    disagree about how a tank drains.
    """
    stops: list[FuelStop] = []
    fuel = start_usable
    position = 0.0
    total_gallons = total_cost = total_net_cost = 0.0
    seq = 0

    for idx, gallons in purchases:
        station = stations[idx]
        fuel -= truck.gallons_for(station.mile_marker - position)
        position = station.mile_marker
        arrival = fuel
        fuel += gallons
        seq += 1
        cost = gallons * station.price_per_gallon
        net_cost = gallons * station.net_price_per_gallon
        stops.append(
            FuelStop(
                seq=seq,
                station=station,
                gallons=gallons,
                arrival_gallons=arrival + truck.reserve_gallons,
                departure_gallons=fuel + truck.reserve_gallons,
                cost=cost,
                net_cost=net_cost,
            )
        )
        total_gallons += gallons
        total_cost += cost
        total_net_cost += net_cost

    fuel -= truck.gallons_for(total_miles - position)
    return FuelPlan(
        total_miles=total_miles,
        stops=stops,
        total_gallons=total_gallons,
        total_cost=total_cost,
        total_net_cost=total_net_cost,
        arrival_gallons=fuel + truck.reserve_gallons,
        feasible=True,
    )


def _solve(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_usable: float,
    basis: CostBasis,
) -> list[tuple[int, float]]:
    """The greedy itself: returns (station index, gallons) purchases.

    At each station buy only enough to reach the next strictly cheaper station
    within range; if there is none, fill up, because every reachable option costs
    more than here. The destination is treated as a free station so the last
    purchase is never larger than the trip needs.
    """
    purchases: list[tuple[int, float]] = []
    fuel = start_usable
    position = 0.0

    for i, station in enumerate(stations):
        fuel -= truck.gallons_for(station.mile_marker - position)
        position = station.mile_marker
        here = station.price(basis)

        # How far we could go from here on a full tank.
        horizon = position + truck.range_miles

        # The destination behaves like a station selling fuel for nothing: once it
        # is in range, buying more than needed to arrive can never pay off.
        target_mile: float | None = total_miles if total_miles <= horizon + _EPSILON_MILES else None
        for nxt in stations[i + 1 :]:
            if nxt.mile_marker > horizon + _EPSILON_MILES:
                break
            if nxt.price(basis) < here:
                target_mile = nxt.mile_marker
                break

        if target_mile is not None:
            # Buy exactly enough to reach the cheaper option.
            needed = truck.gallons_for(target_mile - position) - fuel
            gallons = max(0.0, needed)
        else:
            # Nothing cheaper is reachable: this is the best price in range, fill up.
            gallons = truck.usable_gallons - fuel

        if gallons > _EPSILON_GALLONS:
            purchases.append((i, gallons))
            fuel += gallons

    return purchases


def optimize_fuel_plan(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_fuel_gallons: float,
    basis: CostBasis = "pump",
    stop_overhead_usd: float = DEFAULT_STOP_OVERHEAD_USD,
) -> FuelPlan:
    """Cheapest way to fuel the trip, on the given cost basis.

    ``stop_overhead_usd`` keeps the answer operationally sane. The pure optimum will
    happily buy 0.1 gallons at one stop to reach a slightly cheaper one a mile later:
    right to the cent, and worthless to a driver who loses a quarter of an hour
    pulling in and out. So a stop is dropped when doing without it costs less than
    the stop is worth in time.

    Note this is a price on the driver's time, not a gallon threshold. A threshold
    would throw away small purchases at genuinely cheap stations and cost several
    percent; this only ever gives up money that was never worth stopping for.
    """
    usable, start_usable = _prepare(total_miles, stations, truck, start_fuel_gallons)
    reason = _check_feasible(total_miles, usable, truck, start_usable)
    if reason is not None:
        return FuelPlan(total_miles=total_miles, feasible=False, infeasible_reason=reason)

    # Collapsing can only widen the gaps between stations, so make sure the trip is
    # still fuellable before accepting the shorter list.
    collapsed = _collapse_clusters(usable, basis)
    candidates = (
        collapsed
        if _check_feasible(total_miles, collapsed, truck, start_usable) is None
        else usable
    )
    purchases = _solve(total_miles, candidates, truck, start_usable, basis)
    plan = _build_plan(total_miles, candidates, truck, start_usable, purchases)

    if stop_overhead_usd <= 0:
        return plan

    # Remove token purchases and re-solve, repeatedly. All of them go at once each
    # pass, because along a dense stretch of interstate the station a mile further
    # on is just as marginal: drop them one at a time and the token stop simply
    # moves next door.
    #
    # The guard is measured against the unconstrained optimum, never against the
    # previous pass — judging each step on its own would let a chain of individually
    # reasonable trades add up to an unreasonable total. Money may only be given up
    # in proportion to the stops the driver no longer has to make.
    pure_cost = plan.cost_on(basis)
    pure_stops = plan.stop_count

    for _ in range(_MAX_REFINEMENTS):
        trivial = {i for i, gallons in purchases if gallons < _TOKEN_PURCHASE_GALLONS}
        if not trivial:
            break

        pruned = [s for i, s in enumerate(candidates) if i not in trivial]
        if _check_feasible(total_miles, pruned, truck, start_usable) is not None:
            # Those stops are small but load-bearing: without them the trip cannot
            # be fuelled at all, and arriving beats tidiness.
            break

        trial_purchases = _solve(total_miles, pruned, truck, start_usable, basis)
        trial = _build_plan(total_miles, pruned, truck, start_usable, trial_purchases)

        stops_saved = pure_stops - trial.stop_count
        if trial.cost_on(basis) - pure_cost > stop_overhead_usd * max(stops_saved, 0):
            # Those small purchases are buying real money, not just tidiness.
            break

        candidates, purchases, plan = pruned, trial_purchases, trial

    return plan


def baseline_fuel_plan(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_fuel_gallons: float,
) -> FuelPlan:
    """What the trip costs without any guidance — the status quo we are beating.

    Models a driver who watches only the gauge: keep rolling while the next station
    is still reachable, and when it is not, fill the tank right here.

    One deliberate concession to fairness: the fill is capped at what the rest of the
    trip actually needs, so this plan buys exactly as many gallons as the optimized
    one. Without that cap the baseline ends the trip with a tank full of unburned
    fuel and "costs" more simply for having bought more — which would inflate the
    savings figure into fiction. With it, the two plans price identical fuel and the
    difference between them is purely the choice of where to buy.
    """
    usable, start_usable = _prepare(total_miles, stations, truck, start_fuel_gallons)
    reason = _check_feasible(total_miles, usable, truck, start_usable)
    if reason is not None:
        return FuelPlan(total_miles=total_miles, feasible=False, infeasible_reason=reason)

    purchases: list[tuple[int, float]] = []
    fuel = start_usable
    position = 0.0

    for i, station in enumerate(usable):
        fuel -= truck.gallons_for(station.mile_marker - position)
        position = station.mile_marker

        next_mile = usable[i + 1].mile_marker if i + 1 < len(usable) else total_miles
        if truck.gallons_for(next_mile - position) > fuel + _EPSILON_GALLONS:
            remaining_need = truck.gallons_for(total_miles - position) - fuel
            gallons = min(truck.usable_gallons - fuel, remaining_need)
            if gallons > _EPSILON_GALLONS:
                purchases.append((i, gallons))
                fuel += gallons

    return _build_plan(total_miles, usable, truck, start_usable, purchases)


def compare_plans(
    total_miles: float,
    stations: list[StationCandidate],
    truck: TruckSpec,
    start_fuel_gallons: float,
    basis: CostBasis = "pump",
    stop_overhead_usd: float = DEFAULT_STOP_OVERHEAD_USD,
) -> PlanComparison:
    """Optimized plan, naive baseline, and the money between them."""
    optimized = optimize_fuel_plan(
        total_miles, stations, truck, start_fuel_gallons, basis, stop_overhead_usd
    )
    baseline = baseline_fuel_plan(total_miles, stations, truck, start_fuel_gallons)

    savings = baseline.cost_on(basis) - optimized.cost_on(basis)
    base_cost = baseline.cost_on(basis)
    pct = (savings / base_cost * 100.0) if base_cost > 0 else 0.0
    return PlanComparison(
        optimized=optimized,
        baseline=baseline,
        basis=basis,
        savings_usd=savings,
        savings_pct=pct,
    )


def shift_stations_to_position(
    stations: list[StationCandidate], consumed_miles: float
) -> list[StationCandidate]:
    """Re-base station mile markers onto a route that now starts mid-trip.

    Used by the reroute endpoint: the truck is already 400 miles along, so stations
    behind it are dropped and the rest move 400 miles closer.
    """
    shifted = []
    for s in stations:
        if s.mile_marker < consumed_miles - _EPSILON_MILES:
            continue
        shifted.append(replace(s, mile_marker=s.mile_marker - consumed_miles))
    return shifted

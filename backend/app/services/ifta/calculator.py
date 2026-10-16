"""Per-state mileage, gallons and fuel tax for a route.

This is the raw material of an IFTA return: a carrier owes fuel tax to each state
in proportion to the miles driven there, and gets credit for the tax already paid
at the pump in whichever state it fuelled. The MVP does not file returns — it uses
the same numbers to answer "what does this gallon really cost us", which is what
makes the pump/net switch meaningful.

Boundary accuracy caveat: the seeded state polygons come from Natural Earth, whose
river borders (Mississippi, Ohio) sit a mile or two off the legal line. That is
immaterial for cost comparison but not good enough to file with — swap in the US
Census TIGER boundaries before anyone submits a return from this data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.geo.simplify import linestring_wkt, simplify
from app.services.optimizer.fuel_plan import FuelPlan, TruckSpec

METERS_PER_MILE = 1609.344

_STATE_SPLIT_SQL = text(
    """
WITH route AS (
    SELECT ST_GeomFromText(:wkt, 4326) AS g,
           ST_Transform(ST_GeomFromText(:wkt, 4326), 5070) AS g_m
)
SELECT st.code AS state_code,
       ST_Length(ST_Intersection(route.g_m, ST_Transform(st.geom, 5070))) / :meters_per_mile
           AS miles
FROM us_states st, route
WHERE st.geom && route.g
  AND ST_Intersects(st.geom, route.g)
ORDER BY miles DESC
"""
)

_RATES_SQL = text(
    """
SELECT DISTINCT ON (state_code) state_code, tax_per_gallon
FROM ifta_rates
WHERE fuel_type = :fuel_type AND effective_from <= :as_of
ORDER BY state_code, effective_from DESC
"""
)


@dataclass(frozen=True)
class StateSegment:
    state_code: str
    miles: float
    gallons: float
    tax_per_gallon: float
    tax_owed: float


@dataclass(frozen=True)
class IftaBreakdown:
    segments: list[StateSegment]
    total_miles: float
    total_gallons: float
    total_tax_owed: float
    tax_paid_at_pump: float

    @property
    def net_balance(self) -> float:
        """Positive means more tax is owed than was paid at the pump.

        Fuelling in a low-tax state while driving in a high-tax one does not dodge
        the tax — IFTA settles the difference. That is exactly why the optimizer's
        "net" basis exists.
        """
        return self.total_tax_owed - self.tax_paid_at_pump


async def state_mileage(
    session: AsyncSession,
    route_points: list[tuple[float, float]],
    total_miles: float,
    simplify_tolerance_meters: float = 200.0,
) -> list[tuple[str, float]]:
    """Split the route into per-state mileage, scaled to the provider's total.

    The geometric lengths are rescaled so they sum to the road mileage the routing
    provider reported. Without that, polyline simplification and the small gaps
    between neighbouring state polygons would leave the parts not quite adding up
    to the whole, and every downstream number would be a little bit wrong.
    """
    if len(route_points) < 2:
        return []

    wkt = linestring_wkt(simplify(route_points, simplify_tolerance_meters))
    rows = (
        await session.execute(
            _STATE_SPLIT_SQL, {"wkt": wkt, "meters_per_mile": METERS_PER_MILE}
        )
    ).mappings()

    raw = [(row["state_code"], float(row["miles"] or 0.0)) for row in rows]
    raw = [(code, miles) for code, miles in raw if miles > 0.01]
    measured = sum(miles for _, miles in raw)
    if measured <= 0:
        return []

    scale = total_miles / measured
    return [(code, miles * scale) for code, miles in raw]


async def build_ifta_breakdown(
    session: AsyncSession,
    route_points: list[tuple[float, float]],
    total_miles: float,
    truck: TruckSpec,
    plan: FuelPlan,
    fuel_type: str = "diesel",
    as_of: date | None = None,
) -> IftaBreakdown:
    """Per-state miles, gallons burned there, and the tax that follows."""
    as_of = as_of or date.today()
    split = await state_mileage(session, route_points, total_miles)
    rate_rows = (
        await session.execute(_RATES_SQL, {"fuel_type": fuel_type, "as_of": as_of})
    ).mappings()
    rates = {row["state_code"]: float(row["tax_per_gallon"]) for row in rate_rows}

    segments: list[StateSegment] = []
    for code, miles in split:
        # Gallons burned in a state follow the miles driven there, not where the
        # fuel was bought — that split is the whole mechanic of IFTA.
        gallons = truck.gallons_for(miles)
        rate = rates.get(code, 0.0)
        segments.append(
            StateSegment(
                state_code=code,
                miles=miles,
                gallons=gallons,
                tax_per_gallon=rate,
                tax_owed=gallons * rate,
            )
        )

    paid = sum(stop.gallons * stop.station.tax_per_gallon for stop in plan.stops)
    return IftaBreakdown(
        segments=segments,
        total_miles=sum(s.miles for s in segments),
        total_gallons=sum(s.gallons for s in segments),
        total_tax_owed=sum(s.tax_owed for s in segments),
        tax_paid_at_pump=paid,
    )

"""Route planning: routing provider -> corridor -> optimizer -> IFTA -> database.

This is the only place that knows the whole flow. Each piece it calls is
independently testable, and the flow itself is kept linear on purpose so that the
reroute path can reuse it verbatim with a different origin.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Route, RouteFuelStop, RouteStateSegment, TruckProfile
from app.services.geo.corridor import find_corridor_stations
from app.services.geo.simplify import linestring_wkt, simplify
from app.services.ifta.calculator import IftaBreakdown, build_ifta_breakdown
from app.services.optimizer.fuel_plan import (
    DEFAULT_STOP_OVERHEAD_USD,
    CostBasis,
    PlanComparison,
    StationCandidate,
    TruckSpec,
    compare_plans,
)
from app.services.routing.base import RouteProvider, RouteResult, TruckDimensions, Waypoint

logger = logging.getLogger(__name__)

# Geometry stored for display/history is simplified more gently than the copy used
# for spatial queries: it has to look right when drawn on a map.
_STORED_GEOMETRY_TOLERANCE_M = 50.0


@dataclass
class PlanRequest:
    origin: Waypoint
    destination: Waypoint
    truck: TruckProfile
    tenant_id: uuid.UUID
    start_fuel_gallons: float
    ifta_mode: CostBasis = "pump"
    corridor_miles: float = 3.0
    fuel_type: str = "diesel"
    stop_overhead_usd: float = DEFAULT_STOP_OVERHEAD_USD
    as_of: date | None = None


@dataclass
class PlanResult:
    route: RouteResult
    comparison: PlanComparison
    ifta: IftaBreakdown
    candidates: list[StationCandidate]
    warnings: list[str] = field(default_factory=list)

    @property
    def plan(self):
        return self.comparison.optimized


def truck_spec(truck: TruckProfile) -> TruckSpec:
    return TruckSpec(
        mpg=truck.mpg,
        tank_gallons=truck.tank_gallons,
        reserve_fraction=truck.reserve_fraction,
    )


def truck_dimensions(truck: TruckProfile) -> TruckDimensions:
    return TruckDimensions(
        height_m=truck.height_m,
        width_m=truck.width_m,
        length_m=truck.length_m,
        weight_kg=truck.weight_kg,
        axles=truck.axles,
    )


async def plan_route(
    session: AsyncSession,
    provider: RouteProvider,
    request: PlanRequest,
) -> PlanResult:
    """Build a truck route and the cheapest fuel plan along it."""
    spec = truck_spec(request.truck)
    start_fuel = min(request.start_fuel_gallons, request.truck.tank_gallons)

    route = await provider.route(
        [request.origin, request.destination], truck_dimensions(request.truck)
    )
    warnings = list(route.warnings)
    if not route.truck_legal:
        logger.warning("route computed with a non-truck profile: %s", route.profile_used)

    candidates = await find_corridor_stations(
        session,
        route_points=route.points,
        total_miles=route.distance_miles,
        tenant_id=request.tenant_id,
        corridor_miles=request.corridor_miles,
        fuel_type=request.fuel_type,
        as_of=request.as_of,
    )
    if not candidates:
        warnings.append(
            f"No card-accepting station with a known price was found within "
            f"{request.corridor_miles:g} mi of this route. Widen the corridor or "
            f"refresh fuel prices."
        )

    comparison = compare_plans(
        total_miles=route.distance_miles,
        stations=candidates,
        truck=spec,
        start_fuel_gallons=start_fuel,
        basis=request.ifta_mode,
        stop_overhead_usd=request.stop_overhead_usd,
    )
    if not comparison.optimized.feasible:
        warnings.append(comparison.optimized.infeasible_reason or "no feasible fuel plan")

    ifta = await build_ifta_breakdown(
        session,
        route_points=route.points,
        total_miles=route.distance_miles,
        truck=spec,
        plan=comparison.optimized,
        fuel_type=request.fuel_type,
        as_of=request.as_of,
    )

    return PlanResult(
        route=route,
        comparison=comparison,
        ifta=ifta,
        candidates=candidates,
        warnings=warnings,
    )


async def persist_plan(
    session: AsyncSession,
    request: PlanRequest,
    result: PlanResult,
) -> Route:
    """Store the route, its stops and its per-state split.

    Everything is saved even when the plan is infeasible: knowing that a lane
    cannot be fuelled with the current station coverage is itself useful history.
    """
    plan = result.comparison.optimized
    geometry = linestring_wkt(simplify(result.route.points, _STORED_GEOMETRY_TOLERANCE_M))

    row = Route(
        tenant_id=request.tenant_id,
        truck_profile_id=request.truck.id,
        origin_label=request.origin.label or f"{request.origin.lat:.4f},{request.origin.lon:.4f}",
        origin_lat=request.origin.lat,
        origin_lon=request.origin.lon,
        destination_label=(
            request.destination.label
            or f"{request.destination.lat:.4f},{request.destination.lon:.4f}"
        ),
        destination_lat=request.destination.lat,
        destination_lon=request.destination.lon,
        geometry=func.ST_GeomFromText(geometry, 4326),
        total_miles=result.route.distance_miles,
        total_minutes=result.route.duration_minutes,
        ifta_mode=request.ifta_mode,
        corridor_miles=request.corridor_miles,
        start_fuel_gallons=request.start_fuel_gallons,
        total_fuel_cost=round(plan.total_cost, 2),
        total_gallons=plan.total_gallons,
        baseline_cost=round(result.comparison.baseline.total_cost, 2),
        savings_usd=round(result.comparison.savings_usd, 2),
        feasible=plan.feasible,
        warnings=result.warnings or None,
        provider_meta=result.route.raw_meta,
    )
    session.add(row)
    await session.flush()

    for stop in plan.stops:
        station_id = None
        try:
            station_id = uuid.UUID(stop.station.station_id)
        except (ValueError, AttributeError):
            # Synthetic candidates (tests, fixtures) have non-UUID ids; the stop is
            # still worth keeping, just without the foreign key.
            pass
        session.add(
            RouteFuelStop(
                route_id=row.id,
                station_id=station_id,
                seq=stop.seq,
                stop_type="fuel",
                mile_marker=stop.mile_marker,
                detour_miles=stop.station.detour_miles,
                gallons=stop.gallons,
                price_per_gallon=stop.station.price_per_gallon,
                net_price_per_gallon=stop.station.net_price_per_gallon,
                cost=round(stop.cost, 2),
                arrival_gallons=stop.arrival_gallons,
                departure_gallons=stop.departure_gallons,
            )
        )

    for segment in result.ifta.segments:
        session.add(
            RouteStateSegment(
                route_id=row.id,
                state_code=segment.state_code,
                miles=segment.miles,
                gallons=segment.gallons,
                tax_per_gallon=segment.tax_per_gallon,
                tax_owed=round(segment.tax_owed, 2),
            )
        )

    await session.flush()
    return row

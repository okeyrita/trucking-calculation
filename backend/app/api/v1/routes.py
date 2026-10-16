"""Route planning and history — the module's main surface."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import (
    RouteProviderDep,
    SessionDep,
    TenantDep,
    resolve_location,
    resolve_truck,
)
from app.models import FuelStation, Route
from app.schemas.common import GeoJsonLineString
from app.schemas.route import (
    FuelStopOut,
    IftaSummaryOut,
    RerouteRequest,
    RouteListItem,
    RoutePlanRequest,
    RoutePlanResponse,
    SavedRouteDetail,
    SavingsOut,
    StateSegmentOut,
)
from app.services.optimizer.fuel_plan import DEFAULT_STOP_OVERHEAD_USD
from app.services.planner import PlanRequest, PlanResult, persist_plan, plan_route
from app.services.routing.base import RoutingError, Waypoint

router = APIRouter(prefix="/routes", tags=["routes"])


def _geometry(points: list[tuple[float, float]]) -> GeoJsonLineString:
    # GeoJSON wants [lon, lat].
    return GeoJsonLineString(coordinates=[[lon, lat] for lat, lon in points])


def _build_response(
    request: PlanRequest, result: PlanResult, route_id: uuid.UUID | None
) -> RoutePlanResponse:
    plan = result.comparison.optimized
    return RoutePlanResponse(
        route_id=route_id,
        origin_label=request.origin.label,
        destination_label=request.destination.label,
        total_miles=round(result.route.distance_miles, 1),
        total_minutes=round(result.route.duration_minutes, 1),
        geometry=_geometry(result.route.points),
        profile_used=result.route.profile_used,
        truck_legal=result.route.truck_legal,
        feasible=plan.feasible,
        infeasible_reason=plan.infeasible_reason,
        total_gallons=round(plan.total_gallons, 1),
        total_fuel_cost=round(plan.total_cost, 2),
        arrival_gallons=round(plan.arrival_gallons, 1),
        stops=[
            FuelStopOut(
                seq=stop.seq,
                station_id=stop.station.station_id,
                name=stop.station.name,
                state=stop.station.state,
                lat=stop.station.lat,
                lon=stop.station.lon,
                mile_marker=round(stop.mile_marker, 1),
                detour_miles=round(stop.station.detour_miles, 2),
                gallons=round(stop.gallons, 1),
                price_per_gallon=round(stop.station.price_per_gallon, 3),
                net_price_per_gallon=round(stop.station.net_price_per_gallon, 3),
                cost=round(stop.cost, 2),
                arrival_gallons=round(stop.arrival_gallons, 1),
                departure_gallons=round(stop.departure_gallons, 1),
            )
            for stop in plan.stops
        ],
        candidates_considered=len(result.candidates),
        savings=SavingsOut(
            optimized_cost=round(result.comparison.optimized.cost_on(request.ifta_mode), 2),
            baseline_cost=round(result.comparison.baseline.cost_on(request.ifta_mode), 2),
            savings_usd=round(result.comparison.savings_usd, 2),
            savings_pct=round(result.comparison.savings_pct, 2),
            basis=request.ifta_mode,
        ),
        ifta=IftaSummaryOut(
            mode=request.ifta_mode,
            segments=[
                StateSegmentOut(
                    state_code=segment.state_code,
                    miles=round(segment.miles, 1),
                    gallons=round(segment.gallons, 1),
                    tax_per_gallon=round(segment.tax_per_gallon, 4),
                    tax_owed=round(segment.tax_owed, 2),
                )
                for segment in result.ifta.segments
            ],
            total_tax_owed=round(result.ifta.total_tax_owed, 2),
            tax_paid_at_pump=round(result.ifta.tax_paid_at_pump, 2),
            net_balance=round(result.ifta.net_balance, 2),
        ),
        warnings=result.warnings,
    )


@router.post("/plan", response_model=RoutePlanResponse)
async def plan(
    payload: RoutePlanRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    provider: RouteProviderDep,
):
    """Build a truck-legal route and the cheapest way to fuel it."""
    truck = await resolve_truck(session, tenant_id, payload.truck_profile_id)
    origin = await resolve_location(provider, payload.origin)
    destination = await resolve_location(provider, payload.destination)

    request = PlanRequest(
        origin=origin,
        destination=destination,
        truck=truck,
        tenant_id=tenant_id,
        # A truck that just left the yard is normally full; that is the default so
        # the caller does not have to know the tank size.
        start_fuel_gallons=(
            truck.tank_gallons
            if payload.start_fuel_gallons is None
            else min(payload.start_fuel_gallons, truck.tank_gallons)
        ),
        ifta_mode=payload.ifta_mode,
        corridor_miles=payload.corridor_miles,
        fuel_type=payload.fuel_type,
        stop_overhead_usd=payload.stop_overhead_usd,
    )

    try:
        result = await plan_route(session, provider, request)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    route_id = None
    if payload.save:
        row = await persist_plan(session, request, result)
        route_id = row.id

    return _build_response(request, result, route_id)


@router.get("", response_model=list[RouteListItem])
async def list_routes(
    session: SessionDep,
    tenant_id: TenantDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = (
        await session.execute(
            select(Route)
            .where(Route.tenant_id == tenant_id)
            .order_by(Route.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return [RouteListItem.model_validate(row) for row in rows]


async def _load_route(session, tenant_id: uuid.UUID, route_id: uuid.UUID) -> Route:
    row = (
        await session.execute(
            select(Route)
            .where(Route.id == route_id, Route.tenant_id == tenant_id)
            .options(selectinload(Route.stops), selectinload(Route.state_segments))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="route not found")
    return row


@router.get("/{route_id}", response_model=SavedRouteDetail)
async def get_route(route_id: uuid.UUID, session: SessionDep, tenant_id: TenantDep):
    row = await _load_route(session, tenant_id, route_id)
    geojson = (
        await session.execute(
            select(func.ST_AsGeoJSON(Route.geometry)).where(Route.id == row.id)
        )
    ).scalar_one()

    coordinates = json.loads(geojson)["coordinates"]

    # Station names live on the related station rows; a stop whose station was
    # deleted keeps its numbers and loses only the label.
    stop_names: dict[uuid.UUID, tuple[str, str, float, float]] = {}
    if row.stops:
        station_ids = [s.station_id for s in row.stops if s.station_id]
        if station_ids:
            station_rows = await session.execute(
                select(
                    FuelStation.id,
                    FuelStation.name,
                    FuelStation.brand,
                    FuelStation.state,
                    func.ST_Y(FuelStation.geom),
                    func.ST_X(FuelStation.geom),
                ).where(FuelStation.id.in_(station_ids))
            )
            for sid, name, brand, state, lat, lon in station_rows.all():
                label = f"{brand} — {name}" if brand and brand not in name else name
                stop_names[sid] = (label, state, lat, lon)

    stops = []
    for stop in row.stops:
        label, state, lat, lon = stop_names.get(
            stop.station_id, ("(station removed)", "", None, None)
        )
        stops.append(
            FuelStopOut(
                seq=stop.seq,
                station_id=str(stop.station_id) if stop.station_id else None,
                name=label,
                state=state,
                lat=lat,
                lon=lon,
                mile_marker=round(stop.mile_marker, 1),
                detour_miles=round(stop.detour_miles, 2),
                gallons=round(stop.gallons, 1),
                price_per_gallon=float(stop.price_per_gallon),
                net_price_per_gallon=float(stop.net_price_per_gallon),
                cost=float(stop.cost),
                arrival_gallons=round(stop.arrival_gallons, 1),
                departure_gallons=round(stop.departure_gallons, 1),
            )
        )

    return SavedRouteDetail(
        id=row.id,
        created_at=row.created_at,
        origin_label=row.origin_label,
        destination_label=row.destination_label,
        origin=[row.origin_lat, row.origin_lon],
        destination=[row.destination_lat, row.destination_lon],
        total_miles=round(row.total_miles, 1),
        total_minutes=round(row.total_minutes, 1),
        geometry=GeoJsonLineString(coordinates=coordinates),
        ifta_mode=row.ifta_mode,
        corridor_miles=row.corridor_miles,
        start_fuel_gallons=row.start_fuel_gallons,
        feasible=row.feasible,
        total_gallons=round(row.total_gallons, 1),
        total_fuel_cost=float(row.total_fuel_cost),
        baseline_cost=float(row.baseline_cost),
        savings_usd=float(row.savings_usd),
        stops=stops,
        state_segments=[
            StateSegmentOut(
                state_code=segment.state_code,
                miles=round(segment.miles, 1),
                gallons=round(segment.gallons, 1),
                tax_per_gallon=float(segment.tax_per_gallon),
                tax_owed=float(segment.tax_owed),
            )
            for segment in sorted(row.state_segments, key=lambda s: -s.miles)
        ],
        warnings=row.warnings or [],
    )


@router.post("/{route_id}/reroute", response_model=RoutePlanResponse)
async def reroute(
    route_id: uuid.UUID,
    payload: RerouteRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    provider: RouteProviderDep,
):
    """Replan from where the truck is now to the original destination.

    This is how the module copes with a closed road, weather or a delay: the
    remaining trip is planned fresh against today's prices and the fuel actually
    in the tank, rather than patching the old plan.
    """
    original = await _load_route(session, tenant_id, route_id)
    truck = await resolve_truck(session, tenant_id, original.truck_profile_id)
    current = await resolve_location(provider, payload.current_position)

    request = PlanRequest(
        origin=current,
        destination=Waypoint(
            lat=original.destination_lat,
            lon=original.destination_lon,
            label=original.destination_label,
        ),
        truck=truck,
        tenant_id=tenant_id,
        start_fuel_gallons=min(payload.current_fuel_gallons, truck.tank_gallons),
        ifta_mode=payload.ifta_mode or original.ifta_mode,
        corridor_miles=payload.corridor_miles or original.corridor_miles,
        stop_overhead_usd=(
            payload.stop_overhead_usd
            if payload.stop_overhead_usd is not None
            else DEFAULT_STOP_OVERHEAD_USD
        ),
    )

    try:
        result = await plan_route(session, provider, request)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    route_id_out = None
    if payload.save:
        row = await persist_plan(session, request, result)
        route_id_out = row.id

    return _build_response(request, result, route_id_out)

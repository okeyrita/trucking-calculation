"""Route planning schemas — the shape of the product's main endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import GeoJsonLineString, IftaMode, LocationIn


class RoutePlanRequest(BaseModel):
    origin: LocationIn
    destination: LocationIn
    truck_profile_id: uuid.UUID | None = Field(
        default=None, description="defaults to the tenant's first profile"
    )
    start_fuel_gallons: float | None = Field(
        default=None,
        ge=0,
        description="fuel on board at departure; defaults to a full tank",
    )
    ifta_mode: IftaMode = Field(
        default="pump",
        description=(
            "'pump' optimizes on the price on the stele; 'net' optimizes on price "
            "minus the state's IFTA fuel tax, i.e. the company's real cost"
        ),
    )
    corridor_miles: float = Field(
        default=3.0, gt=0, le=50, description="how far off-route a station may be"
    )
    fuel_type: str = Field(default="diesel", max_length=20)
    stop_overhead_usd: float = Field(
        default=8.0,
        ge=0,
        le=200,
        description=(
            "What a fuel stop costs beyond the fuel — driver time, detour, "
            "manoeuvring. Stops that save less than this are merged away. Set 0 for "
            "the pure mathematical optimum, which may include token purchases no "
            "driver would make."
        ),
    )
    save: bool = Field(default=True, description="store the plan in history")


class RerouteRequest(BaseModel):
    current_position: LocationIn
    current_fuel_gallons: float = Field(ge=0)
    ifta_mode: IftaMode | None = None
    corridor_miles: float | None = Field(default=None, gt=0, le=50)
    stop_overhead_usd: float | None = Field(default=None, ge=0, le=200)
    save: bool = True


class FuelStopOut(BaseModel):
    seq: int
    station_id: str | None
    name: str
    state: str
    lat: float | None
    lon: float | None
    mile_marker: float
    detour_miles: float
    gallons: float
    price_per_gallon: float
    net_price_per_gallon: float
    cost: float
    arrival_gallons: float
    departure_gallons: float


class StateSegmentOut(BaseModel):
    state_code: str
    miles: float
    gallons: float
    tax_per_gallon: float
    tax_owed: float


class IftaSummaryOut(BaseModel):
    mode: IftaMode
    segments: list[StateSegmentOut]
    total_tax_owed: float
    tax_paid_at_pump: float
    net_balance: float = Field(
        description="tax owed minus tax already paid at the pump; positive means a bill"
    )


class SavingsOut(BaseModel):
    optimized_cost: float
    baseline_cost: float
    savings_usd: float
    savings_pct: float
    basis: IftaMode
    baseline_description: str = (
        "What the same trip costs if the driver fills up at the last station they "
        "can still reach, ignoring price — the behaviour this product replaces."
    )


class RoutePlanResponse(BaseModel):
    route_id: uuid.UUID | None
    origin_label: str
    destination_label: str
    total_miles: float
    total_minutes: float
    geometry: GeoJsonLineString
    profile_used: str
    truck_legal: bool = Field(
        description="false when a car profile was used and truck restrictions may be ignored"
    )
    feasible: bool
    infeasible_reason: str | None = None

    total_gallons: float
    total_fuel_cost: float
    arrival_gallons: float
    stops: list[FuelStopOut]
    candidates_considered: int

    savings: SavingsOut
    ifta: IftaSummaryOut
    warnings: list[str] = []


class RouteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    origin_label: str
    destination_label: str
    total_miles: float
    total_minutes: float
    ifta_mode: str
    total_fuel_cost: float
    baseline_cost: float
    savings_usd: float
    feasible: bool
    created_at: datetime


class StationOut(BaseModel):
    id: uuid.UUID
    name: str
    brand: str | None
    state: str
    lat: float
    lon: float
    accepts_card: bool
    price_per_gallon: float | None = None
    price_date: str | None = None


class GeocodeResult(BaseModel):
    label: str
    lat: float
    lon: float


class SavedRouteDetail(BaseModel):
    """A route as it was stored, rebuilt from the database rather than recomputed.

    Prices move daily, so replanning an old route would quietly give different
    numbers than the ones the dispatcher acted on. History must show what was
    actually recommended at the time.
    """

    id: uuid.UUID
    created_at: datetime
    origin_label: str
    destination_label: str
    origin: list[float]
    destination: list[float]
    total_miles: float
    total_minutes: float
    geometry: GeoJsonLineString
    ifta_mode: str
    corridor_miles: float
    start_fuel_gallons: float
    feasible: bool
    total_gallons: float
    total_fuel_cost: float
    baseline_cost: float
    savings_usd: float
    stops: list[FuelStopOut]
    state_segments: list[StateSegmentOut]
    warnings: list[str] = []

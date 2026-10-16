"""SQLAlchemy models. Imported here so Alembic autogenerate sees every table."""

from app.models.fuel import (
    FuelPrice,
    FuelStation,
    IftaRate,
    ScraperSession,
    UsState,
)
from app.models.route import Route, RouteFuelStop, RouteStateSegment
from app.models.tenant import DEFAULT_TENANT_ID, Tenant
from app.models.truck import TruckProfile

__all__ = [
    "DEFAULT_TENANT_ID",
    "FuelPrice",
    "FuelStation",
    "IftaRate",
    "Route",
    "RouteFuelStop",
    "RouteStateSegment",
    "ScraperSession",
    "Tenant",
    "TruckProfile",
    "UsState",
]

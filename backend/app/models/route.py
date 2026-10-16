import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import created_at, pk, tenant_fk


class Route(Base):
    """A planned trip: the truck-legal geometry plus the costed fuel plan.

    `baseline_cost` is what the same trip would cost if the driver simply filled
    up at the first reachable station once low — the behaviour the product exists
    to replace. `savings_usd` is the difference, and it is the number the customer
    actually cares about.
    """

    __tablename__ = "routes"
    __table_args__ = (Index("ix_routes_geometry", "geometry", postgresql_using="gist"),)

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    truck_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("truck_profiles.id", ondelete="RESTRICT")
    )

    origin_label: Mapped[str] = mapped_column(String(300), nullable=False)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lon: Mapped[float] = mapped_column(Float, nullable=False)
    destination_label: Mapped[str] = mapped_column(String(300), nullable=False)
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lon: Mapped[float] = mapped_column(Float, nullable=False)

    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=False
    )
    total_miles: Mapped[float] = mapped_column(Float, nullable=False)
    total_minutes: Mapped[float] = mapped_column(Float, nullable=False)

    # "pump" = optimize on the price on the stele; "net" = on price minus the
    # state's IFTA tax, i.e. the company's true cost after the tax credit.
    ifta_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="pump")
    corridor_miles: Mapped[float] = mapped_column(Float, nullable=False)
    start_fuel_gallons: Mapped[float] = mapped_column(Float, nullable=False)

    total_fuel_cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_gallons: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    savings_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    feasible: Mapped[bool] = mapped_column(nullable=False, default=True)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    provider_meta: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = created_at()

    stops: Mapped[list["RouteFuelStop"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteFuelStop.seq",
    )
    state_segments: Mapped[list["RouteStateSegment"]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )


class RouteFuelStop(Base):
    """One recommended stop. `stop_type` is already here so HOS rest stops can be
    interleaved later without a schema change (HOS itself is out of MVP scope)."""

    __tablename__ = "route_fuel_stops"

    id: Mapped[uuid.UUID] = pk()
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), index=True
    )
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fuel_stations.id", ondelete="SET NULL")
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_type: Mapped[str] = mapped_column(String(16), nullable=False, default="fuel")

    mile_marker: Mapped[float] = mapped_column(Float, nullable=False)
    detour_miles: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gallons: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_gallon: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    net_price_per_gallon: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    arrival_gallons: Mapped[float] = mapped_column(Float, nullable=False)
    departure_gallons: Mapped[float] = mapped_column(Float, nullable=False)

    route: Mapped[Route] = relationship(back_populates="stops")


class RouteStateSegment(Base):
    """Per-state mileage and gallons burned — the raw material of an IFTA return."""

    __tablename__ = "route_state_segments"

    id: Mapped[uuid.UUID] = pk()
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), index=True
    )
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    miles: Mapped[float] = mapped_column(Float, nullable=False)
    gallons: Mapped[float] = mapped_column(Float, nullable=False)
    tax_per_gallon: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    tax_owed: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    route: Mapped[Route] = relationship(back_populates="state_segments")

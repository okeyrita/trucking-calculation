import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import created_at, pk, tenant_fk


class FuelStation(Base):
    """A truck stop. `accepts_card` is the whole point: the optimizer must only
    ever route to stations where the company's fuel card is honoured."""

    __tablename__ = "fuel_stations"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_fuel_stations_provider_external"),
        Index("ix_fuel_stations_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    geom: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    accepts_card: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_truck_lanes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = created_at()

    prices: Mapped[list["FuelPrice"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class FuelPrice(Base):
    """One price per station per fuel type per day.

    US fuel prices move once a day nationwide, so `effective_date` (not a timestamp)
    is the natural grain. `is_contract_price` distinguishes the company's negotiated
    price from a retail/pump price — the two differ a lot and must not be mixed.
    """

    __tablename__ = "fuel_prices"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "fuel_type", "effective_date", name="uq_fuel_prices_station_type_date"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    station_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fuel_stations.id", ondelete="CASCADE"), index=True
    )
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="diesel")
    price_per_gallon: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    is_contract_price: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="seed")

    created_at: Mapped[datetime] = created_at()

    station: Mapped[FuelStation] = relationship(back_populates="prices")


class IftaRate(Base):
    """State fuel-tax rates, in USD per gallon.

    Kept as a local table on purpose: there is no practical open IFTA API, and the
    rates change quarterly at most, so a seeded table beats any integration.
    """

    __tablename__ = "ifta_rates"
    __table_args__ = (
        UniqueConstraint(
            "state_code", "fuel_type", "effective_from", name="uq_ifta_rates_state_type_from"
        ),
    )

    id: Mapped[uuid.UUID] = pk()
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="diesel")
    tax_per_gallon: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class UsState(Base):
    """State polygons, used to split a route into per-state mileage for IFTA."""

    __tablename__ = "us_states"
    __table_args__ = (Index("ix_us_states_geom", "geom", postgresql_using="gist"),)

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    geom: Mapped[str] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )


class ScraperSession(Base):
    """Persisted Playwright `storage_state` for a portal behind 2FA.

    We never try to defeat 2FA programmatically: a human logs in once via the
    login CLI, the session is stored here and reused until it expires, at which
    point the refresh task flips `status` to `needs_login`.
    """

    __tablename__ = "scraper_sessions"

    id: Mapped[uuid.UUID] = pk()
    provider: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    storage_state: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="needs_login")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at()

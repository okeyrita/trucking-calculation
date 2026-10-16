import uuid
from datetime import datetime

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import created_at, pk, tenant_fk


class TruckProfile(Base):
    """The "virtual tank" of a truck plus the dimensions routing needs.

    Fuel economy is stored as MPG (miles per gallon) — the US convention, which is
    the inverse of L/100km: gallons = miles / mpg, never miles * mpg.
    """

    __tablename__ = "truck_profiles"

    id: Mapped[uuid.UUID] = pk()
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    mpg: Mapped[float] = mapped_column(Float, nullable=False)
    tank_gallons: Mapped[float] = mapped_column(Float, nullable=False)
    # Fraction of the tank the driver must never dip below (safety buffer).
    reserve_fraction: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)

    # Class 8 defaults, in metric units because that is what routing APIs expect.
    height_m: Mapped[float] = mapped_column(Float, nullable=False, default=4.11)
    width_m: Mapped[float] = mapped_column(Float, nullable=False, default=2.59)
    length_m: Mapped[float] = mapped_column(Float, nullable=False, default=22.0)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False, default=36287.0)
    axles: Mapped[int] = mapped_column(nullable=False, default=5)

    created_at: Mapped[datetime] = created_at()

    @property
    def usable_gallons(self) -> float:
        return self.tank_gallons * (1.0 - self.reserve_fraction)

    @property
    def range_miles(self) -> float:
        return self.usable_gallons * self.mpg

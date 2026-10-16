"""Truck profile schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class TruckProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Fuel economy in MPG: a loaded Class 8 tractor runs roughly 5.5-7.5.
    mpg: float = Field(gt=0, le=20, examples=[6.5])
    tank_gallons: float = Field(gt=0, le=500, examples=[200.0])
    reserve_fraction: float = Field(default=0.15, ge=0, lt=1)
    height_m: float = Field(default=4.11, gt=0, le=6)
    width_m: float = Field(default=2.59, gt=0, le=4)
    length_m: float = Field(default=22.0, gt=0, le=40)
    weight_kg: float = Field(default=36287.0, gt=0, le=80000)
    axles: int = Field(default=5, ge=2, le=12)


class TruckProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    mpg: float | None = Field(default=None, gt=0, le=20)
    tank_gallons: float | None = Field(default=None, gt=0, le=500)
    reserve_fraction: float | None = Field(default=None, ge=0, lt=1)
    height_m: float | None = Field(default=None, gt=0, le=6)
    width_m: float | None = Field(default=None, gt=0, le=4)
    length_m: float | None = Field(default=None, gt=0, le=40)
    weight_kg: float | None = Field(default=None, gt=0, le=80000)
    axles: int | None = Field(default=None, ge=2, le=12)


class TruckProfileOut(TruckProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    usable_gallons: float
    range_miles: float

"""Shared request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

IftaMode = Literal["pump", "net"]


class LocationIn(BaseModel):
    """A place, given either as coordinates or as text to geocode.

    Coordinates win when both are supplied, so a UI can send the text it showed the
    user together with the point it resolved to, and get that exact point back.
    """

    query: str | None = Field(default=None, description="e.g. 'Dallas, TX'")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    label: str | None = None

    @model_validator(mode="after")
    def _need_something(self) -> LocationIn:
        has_point = self.lat is not None and self.lon is not None
        if not has_point and not (self.query and self.query.strip()):
            raise ValueError("provide either lat+lon or a query string")
        return self


class GeoJsonLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    # GeoJSON is [longitude, latitude] — the opposite of how coordinates are
    # usually spoken, and the most common source of bugs in this codebase.
    coordinates: list[list[float]]

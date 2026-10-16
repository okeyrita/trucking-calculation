"""Routing provider interface.

Everything downstream (geometry storage, the corridor query, the optimizer) depends
only on :class:`RouteResult`, so swapping GraphHopper Cloud for a self-hosted
instance or for HERE is a new subclass and nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    label: str = ""


@dataclass(frozen=True)
class TruckDimensions:
    """Dimensions a truck-aware router needs, in metric units (API convention)."""

    height_m: float = 4.11
    width_m: float = 2.59
    length_m: float = 22.0
    weight_kg: float = 36287.0
    axles: int = 5


@dataclass(frozen=True)
class RouteResult:
    points: list[tuple[float, float]]  # (lat, lon) along the driven route
    distance_miles: float
    duration_minutes: float
    profile_used: str
    warnings: list[str] = field(default_factory=list)
    raw_meta: dict = field(default_factory=dict)

    @property
    def truck_legal(self) -> bool:
        """False when the route came from a car profile and may ignore bridge
        heights, weight limits and truck-restricted roads."""
        return self.profile_used in {"truck", "small_truck", "scooter_truck"}


class RoutingError(RuntimeError):
    pass


class RouteProvider(ABC):
    @abstractmethod
    async def route(
        self, waypoints: list[Waypoint], dimensions: TruckDimensions
    ) -> RouteResult: ...

    @abstractmethod
    async def geocode(self, query: str, limit: int = 5) -> list[Waypoint]: ...

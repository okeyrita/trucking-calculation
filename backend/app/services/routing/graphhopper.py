"""GraphHopper Cloud routing and geocoding.

Two things about this provider are worth knowing before changing it:

1. The ``truck`` profile is not on every GraphHopper plan. When the plan rejects
   it we fall back to ``car`` and attach a warning rather than failing the request —
   a car route is still useful for a demo, but it may route the truck under a low
   bridge, so the warning is surfaced all the way to the UI and stored on the route.
2. Point order differs between the two endpoints: the POST /route body takes
   ``[lon, lat]`` while GET /geocode returns ``{lat, lng}``. Mixing them up puts
   routes in the Indian Ocean, which is the first thing to check if that happens.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.routing.base import (
    METERS_PER_MILE,
    RouteProvider,
    RouteResult,
    RoutingError,
    TruckDimensions,
    Waypoint,
)
from app.services.routing.polyline import decode_polyline

logger = logging.getLogger(__name__)

_CAR_FALLBACK_WARNING = (
    "GraphHopper rejected the 'truck' profile for this API key, so the route was "
    "computed with the 'car' profile. It may ignore bridge heights, weight limits "
    "and truck-restricted roads — verify before dispatching a driver."
)
_NO_DIMENSIONS_WARNING = (
    "GraphHopper rejected the vehicle dimensions, so the route uses the profile's "
    "default truck dimensions instead of this truck's."
)


class GraphHopperRouteProvider(RouteProvider):
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    def _require_key(self) -> None:
        if not self.settings.graphhopper_api_key:
            raise RoutingError(
                "GRAPHHOPPER_API_KEY is not set. Get a key at "
                "https://graphhopper.com/dashboard/ and put it in .env"
            )

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_key()
        url = f"{self.settings.graphhopper_base_url.rstrip('/')}{path}"
        params = {"key": self.settings.graphhopper_api_key}
        timeout = self.settings.routing_timeout_seconds

        async def send(client: httpx.AsyncClient) -> tuple[int, dict[str, Any]]:
            response = await client.post(url, params=params, json=payload, timeout=timeout)
            try:
                body = response.json()
            except ValueError:
                body = {"message": response.text[:500]}
            return response.status_code, body

        if self._client is not None:
            return await send(self._client)
        async with httpx.AsyncClient() as client:
            return await send(client)

    async def _get(self, path: str, params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_key()
        url = f"{self.settings.graphhopper_base_url.rstrip('/')}{path}"
        params = {**params, "key": self.settings.graphhopper_api_key}
        timeout = self.settings.routing_timeout_seconds

        async def send(client: httpx.AsyncClient) -> tuple[int, dict[str, Any]]:
            response = await client.get(url, params=params, timeout=timeout)
            try:
                body = response.json()
            except ValueError:
                body = {"message": response.text[:500]}
            return response.status_code, body

        if self._client is not None:
            return await send(self._client)
        async with httpx.AsyncClient() as client:
            return await send(client)

    @staticmethod
    def _body(
        waypoints: list[Waypoint], profile: str, dimensions: TruckDimensions | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "profile": profile,
            # POST /route wants [lon, lat].
            "points": [[w.lon, w.lat] for w in waypoints],
            "points_encoded": True,
            "instructions": False,
            "elevation": False,
            "calc_points": True,
            "locale": "en",
        }
        if dimensions is not None:
            body.update(
                {
                    "height": dimensions.height_m,
                    "width": dimensions.width_m,
                    "length": dimensions.length_m,
                    "weight": dimensions.weight_kg,
                    "axles": dimensions.axles,
                }
            )
        return body

    def _parse(self, body: dict[str, Any], profile: str, warnings: list[str]) -> RouteResult:
        paths = body.get("paths") or []
        if not paths:
            raise RoutingError(f"GraphHopper returned no path: {body.get('message', body)}")
        path = paths[0]

        encoded = path.get("points")
        if isinstance(encoded, str):
            points = decode_polyline(encoded)
        elif isinstance(encoded, dict) and "coordinates" in encoded:
            # points_encoded=false comes back as GeoJSON, i.e. [lon, lat].
            points = [(lat, lon) for lon, lat, *_ in encoded["coordinates"]]
        else:
            raise RoutingError("GraphHopper response contained no usable geometry")

        if len(points) < 2:
            raise RoutingError("GraphHopper returned a degenerate route")

        return RouteResult(
            points=points,
            distance_miles=float(path["distance"]) / METERS_PER_MILE,
            duration_minutes=float(path["time"]) / 60000.0,
            profile_used=profile,
            warnings=warnings,
            raw_meta={
                "provider": "graphhopper",
                "profile": profile,
                "distance_meters": path.get("distance"),
                "time_ms": path.get("time"),
                "point_count": len(points),
            },
        )

    async def route(self, waypoints: list[Waypoint], dimensions: TruckDimensions) -> RouteResult:
        if len(waypoints) < 2:
            raise RoutingError("a route needs at least an origin and a destination")

        warnings: list[str] = []
        profile = "truck" if self.settings.routing_truck_profile_enabled else "car"
        dims: TruckDimensions | None = dimensions if profile != "car" else None

        for _attempt in range(3):
            status, body = await self._post("/route", self._body(waypoints, profile, dims))
            if status == 200:
                return self._parse(body, profile, warnings)

            message = str(body.get("message", body))
            logger.warning("GraphHopper %s on profile=%s: %s", status, profile, message[:300])

            # Distinguish "your plan has no truck profile" from "I don't know these
            # dimension fields": the first needs a different profile, the second
            # just needs them dropped.
            lowered = message.lower()
            if status in (400, 401, 403) and "profile" in lowered and profile != "car":
                profile, dims = "car", None
                warnings.append(_CAR_FALLBACK_WARNING)
                continue
            if status == 400 and dims is not None:
                dims = None
                warnings.append(_NO_DIMENSIONS_WARNING)
                continue
            if status == 429:
                raise RoutingError("GraphHopper rate limit reached; try again later")

            raise RoutingError(f"GraphHopper routing failed ({status}): {message[:300]}")

        raise RoutingError("GraphHopper routing failed after retrying with fallbacks")

    async def geocode(self, query: str, limit: int = 5) -> list[Waypoint]:
        status, body = await self._get(
            "/geocode", {"q": query, "limit": limit, "locale": "en", "provider": "default"}
        )
        if status != 200:
            raise RoutingError(f"GraphHopper geocoding failed ({status}): {body.get('message')}")

        results: list[Waypoint] = []
        for hit in body.get("hits", []):
            point = hit.get("point") or {}
            if "lat" not in point or "lng" not in point:
                continue
            parts = [hit.get("name"), hit.get("city"), hit.get("state"), hit.get("country")]
            label = ", ".join(dict.fromkeys(p for p in parts if p))
            results.append(Waypoint(lat=float(point["lat"]), lon=float(point["lng"]), label=label))
        return results

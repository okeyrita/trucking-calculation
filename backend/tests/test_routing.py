"""GraphHopper provider tests, including the fallbacks that keep it usable.

All requests are served by an httpx MockTransport — no network, no API key needed.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.routing.base import RoutingError, TruckDimensions, Waypoint
from app.services.routing.graphhopper import GraphHopperRouteProvider
from tests.conftest import json_response, mock_client

DALLAS = Waypoint(lat=32.7767, lon=-96.7970, label="Dallas, TX")
CHICAGO = Waypoint(lat=41.8781, lon=-87.6298, label="Chicago, IL")
DIMS = TruckDimensions()


async def test_parses_a_successful_route(settings, graphhopper_route_body):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": request.read().decode()})
        return json_response(200, graphhopper_route_body)

    provider = GraphHopperRouteProvider(settings, mock_client(handler))
    result = await provider.route([DALLAS, CHICAGO], DIMS)

    assert result.profile_used == "truck"
    assert result.truck_legal is True
    assert result.distance_miles == pytest.approx(912.2, abs=1.0)
    assert result.duration_minutes == pytest.approx(816.7, abs=1.0)
    assert len(result.points) > 100
    # Geometry must come back as (lat, lon) in the US, not swapped.
    assert 25 < result.points[0][0] < 50
    assert -125 < result.points[0][1] < -66
    # And the request must send [lon, lat], which is the opposite order.
    import json as _json

    assert _json.loads(seen[0]["body"])["points"] == [[-96.797, 32.7767], [-87.6298, 41.8781]]
    assert "key=test-key" in seen[0]["url"]


async def test_falls_back_to_car_when_the_plan_has_no_truck_profile(
    settings, graphhopper_route_body
):
    """A key without the truck profile must still return a route, loudly."""
    profiles: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.read())
        profiles.append(body["profile"])
        if body["profile"] == "truck":
            return json_response(
                400, {"message": "The profile 'truck' is not supported for your API key"}
            )
        return json_response(200, graphhopper_route_body)

    provider = GraphHopperRouteProvider(settings, mock_client(handler))
    result = await provider.route([DALLAS, CHICAGO], DIMS)

    assert profiles == ["truck", "car"]
    assert result.profile_used == "car"
    assert result.truck_legal is False
    assert any("may ignore bridge heights" in w for w in result.warnings)


async def test_retries_without_dimensions_when_they_are_rejected(
    settings, graphhopper_route_body
):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.read())
        bodies.append(body)
        if "height" in body:
            return json_response(400, {"message": "Unknown parameter 'height'"})
        return json_response(200, graphhopper_route_body)

    provider = GraphHopperRouteProvider(settings, mock_client(handler))
    result = await provider.route([DALLAS, CHICAGO], DIMS)

    assert "height" in bodies[0] and "height" not in bodies[1]
    assert result.profile_used == "truck"  # still a truck route, just default dims
    assert any("default truck dimensions" in w for w in result.warnings)


async def test_rate_limit_is_reported_as_such(settings):
    provider = GraphHopperRouteProvider(
        settings, mock_client(lambda r: json_response(429, {"message": "too many"}))
    )
    with pytest.raises(RoutingError, match="rate limit"):
        await provider.route([DALLAS, CHICAGO], DIMS)


async def test_missing_api_key_is_a_clear_error(graphhopper_route_body):
    from app.core.config import Settings

    provider = GraphHopperRouteProvider(Settings(graphhopper_api_key=""))
    with pytest.raises(RoutingError, match="GRAPHHOPPER_API_KEY"):
        await provider.route([DALLAS, CHICAGO], DIMS)


async def test_empty_path_list_is_an_error(settings):
    provider = GraphHopperRouteProvider(
        settings, mock_client(lambda r: json_response(200, {"paths": []}))
    )
    with pytest.raises(RoutingError, match="no path"):
        await provider.route([DALLAS, CHICAGO], DIMS)


async def test_accepts_unencoded_geojson_geometry(settings):
    body = {
        "paths": [
            {
                "distance": 1609.344,
                "time": 60000,
                # points_encoded=false form: GeoJSON, [lon, lat]
                "points": {
                    "type": "LineString",
                    "coordinates": [[-96.797, 32.7767], [-96.8, 32.78]],
                },
            }
        ]
    }
    provider = GraphHopperRouteProvider(settings, mock_client(lambda r: json_response(200, body)))
    result = await provider.route([DALLAS, CHICAGO], DIMS)

    assert result.points[0] == (32.7767, -96.797)
    assert result.distance_miles == pytest.approx(1.0)


async def test_geocode_builds_readable_labels(settings):
    body = {
        "hits": [
            {
                "point": {"lat": 32.7767, "lng": -96.797},
                "name": "Dallas",
                "state": "Texas",
                "country": "United States",
            }
        ]
    }
    provider = GraphHopperRouteProvider(settings, mock_client(lambda r: json_response(200, body)))
    hits = await provider.geocode("Dallas")

    assert hits[0].label == "Dallas, Texas, United States"
    assert (hits[0].lat, hits[0].lon) == (32.7767, -96.797)


async def test_route_needs_two_points(settings):
    provider = GraphHopperRouteProvider(settings, mock_client(lambda r: json_response(200, {})))
    with pytest.raises(RoutingError, match="at least an origin"):
        await provider.route([DALLAS], DIMS)

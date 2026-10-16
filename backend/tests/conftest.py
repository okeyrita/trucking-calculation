"""Shared fixtures.

Nothing here talks to the network. Database-backed tests live in
``test_integration_db.py`` and skip themselves when no PostGIS is reachable.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.services.routing.polyline import encode_polyline

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        graphhopper_api_key="test-key",
        graphhopper_base_url="https://graphhopper.test/api/1",
        routing_truck_profile_enabled=True,
        database_url="postgresql+asyncpg://unused/unused",
    )


@pytest.fixture
def dallas_chicago_points() -> list[tuple[float, float]]:
    """A coarse but real-shaped I-35/I-44/I-55 path, densified for the geometry code."""
    anchors = [
        (32.7767, -96.7970),  # Dallas, TX
        (33.9137, -97.1436),
        (35.4676, -97.5164),  # Oklahoma City, OK
        (36.1540, -95.9928),  # Tulsa, OK
        (37.2090, -93.2923),  # Springfield, MO
        (38.6270, -90.1994),  # St Louis, MO
        (39.8003, -89.6437),  # Springfield, IL
        (41.8781, -87.6298),  # Chicago, IL
    ]
    points: list[tuple[float, float]] = []
    for start, end in zip(anchors, anchors[1:], strict=False):
        for step in range(40):
            t = step / 40
            points.append(
                (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
            )
    points.append(anchors[-1])
    return points


@pytest.fixture
def graphhopper_route_body(dallas_chicago_points):
    """A minimal GraphHopper /route response with real geometry."""
    return {
        "paths": [
            {
                "distance": 1_468_000.0,  # ~912 mi in meters
                "time": 49_000_000,  # ~13.6 h in ms
                "points": encode_polyline(dallas_chicago_points),
                "points_encoded": True,
            }
        ]
    }


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def eia_html() -> str:
    path = FIXTURES / "eia_diesel_table.html"
    return path.read_text(encoding="utf-8")


def json_response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status, content=json.dumps(payload), headers={"content-type": "application/json"}
    )

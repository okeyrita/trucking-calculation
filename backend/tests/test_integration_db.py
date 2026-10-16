"""End-to-end tests against a real PostGIS database.

These are the tests that prove the spatial half of the system: the corridor query,
the per-state split, and the planning endpoint that stitches everything together.
They skip themselves when no database is reachable, so the offline suite stays
runnable anywhere.

Isolation: every row created here belongs to a dedicated test tenant and a
``test`` station provider, so running against a development database does not
disturb real data. The shared reference tables (``us_states``, ``ifta_rates``) are
upserted idempotently.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.models import (
    FuelPrice,
    FuelStation,
    IftaRate,
    Route,
    RouteFuelStop,
    RouteStateSegment,
    Tenant,
    TruckProfile,
    UsState,
)
from app.services.routing.base import RouteProvider, RouteResult, Waypoint

TEST_TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
TEST_PROVIDER = "test"


async def _engine_or_skip():
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT PostGIS_Version()"))
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        await engine.dispose()
        pytest.skip(f"no PostGIS database available: {type(exc).__name__}: {exc}"[:200])
    return engine


@pytest_asyncio.fixture
async def db():
    """A session with the schema present and this test's data cleaned up after."""
    engine = await _engine_or_skip()
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.db import Base

    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _seed_reference_data(session)
        await _clean(session)
        yield session
        await _clean(session)
        await session.commit()
    await engine.dispose()


async def _clean(session) -> None:
    route_ids = (
        await session.execute(select(Route.id).where(Route.tenant_id == TEST_TENANT))
    ).scalars().all()
    if route_ids:
        await session.execute(delete(RouteFuelStop).where(RouteFuelStop.route_id.in_(route_ids)))
        await session.execute(
            delete(RouteStateSegment).where(RouteStateSegment.route_id.in_(route_ids))
        )
        await session.execute(delete(Route).where(Route.id.in_(route_ids)))

    station_ids = (
        await session.execute(select(FuelStation.id).where(FuelStation.provider == TEST_PROVIDER))
    ).scalars().all()
    if station_ids:
        await session.execute(delete(FuelPrice).where(FuelPrice.station_id.in_(station_ids)))
        await session.execute(delete(FuelStation).where(FuelStation.id.in_(station_ids)))

    await session.execute(delete(TruckProfile).where(TruckProfile.tenant_id == TEST_TENANT))
    await session.commit()


async def _seed_reference_data(session) -> None:
    """State polygons and IFTA rates, loaded once and reused."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == TEST_TENANT))
    ).scalar_one_or_none()
    if tenant is None:
        session.add(Tenant(id=TEST_TENANT, name="pytest tenant"))

    states = (await session.execute(select(func.count()).select_from(UsState))).scalar_one()
    if states < 50:
        from app.cli import _seed_states

        await _seed_states(session)

    rates = (await session.execute(select(func.count()).select_from(IftaRate))).scalar_one()
    if rates < 40:
        from app.cli import _seed_ifta

        await _seed_ifta(session)
    await session.commit()


class FakeRouteProvider(RouteProvider):
    """Returns a fixed geometry, so tests never depend on GraphHopper."""

    def __init__(self, points, distance_miles, duration_minutes=800.0, profile="truck"):
        self.points = points
        self.distance_miles = distance_miles
        self.duration_minutes = duration_minutes
        self.profile = profile

    async def route(self, waypoints, dimensions):
        return RouteResult(
            points=self.points,
            distance_miles=self.distance_miles,
            duration_minutes=self.duration_minutes,
            profile_used=self.profile,
            raw_meta={"provider": "fake"},
        )

    async def geocode(self, query, limit=5):
        known = {
            "dallas, tx": (32.7767, -96.7970),
            "chicago, il": (41.8781, -87.6298),
        }
        hit = known.get(query.strip().lower())
        return [Waypoint(lat=hit[0], lon=hit[1], label=query)] if hit else []


async def _add_station(session, name, state, lat, lon, price, accepts_card=True):
    station = FuelStation(
        tenant_id=TEST_TENANT,
        provider=TEST_PROVIDER,
        external_id=f"test:{name}",
        brand="TestStop",
        name=name,
        state=state,
        geom=func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326),
        accepts_card=accepts_card,
    )
    session.add(station)
    await session.flush()
    session.add(
        FuelPrice(
            station_id=station.id,
            fuel_type="diesel",
            price_per_gallon=price,
            is_contract_price=False,
            effective_date=date.today(),
            source=TEST_PROVIDER,
        )
    )
    await session.flush()
    return station


def _straight_line(start, end, steps=200):
    return [
        (start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        for i in range(steps + 1)
    ]


class TestSessionScope:
    def test_survives_repeated_event_loops(self):
        """Regression: a Celery worker runs every task in a fresh event loop.

        The cached engine binds its connection pool to the loop that created it, so
        reusing it across ``asyncio.run()`` calls fails with "attached to a different
        loop" — a worker would serve exactly one task per process and fail every one
        after that. ``session_scope`` builds and disposes its own engine per run.
        """
        import asyncio

        from app.core.db import session_scope

        async def touch_the_database():
            async with session_scope() as session:
                return (await session.execute(text("SELECT 1"))).scalar_one()

        # Three separate loops, exactly as three queued tasks would do it.
        for _ in range(3):
            assert asyncio.run(touch_the_database()) == 1


class TestCorridorQuery:
    async def test_finds_only_stations_near_the_route(self, db, dallas_chicago_points):
        from app.services.geo.corridor import find_corridor_stations

        on_route = await _add_station(db, "on-route", "MO", 38.6270, -90.1994, 5.10)
        far_away = await _add_station(db, "far-away", "FL", 27.9506, -82.4572, 3.00)
        await db.commit()

        found = await find_corridor_stations(
            db, dallas_chicago_points, total_miles=912.0, tenant_id=TEST_TENANT, corridor_miles=10
        )

        ids = {candidate.station_id for candidate in found}
        assert str(on_route.id) in ids
        assert str(far_away.id) not in ids

    async def test_excludes_stations_that_do_not_take_the_card(self, db, dallas_chicago_points):
        from app.services.geo.corridor import find_corridor_stations

        await _add_station(db, "no-card", "MO", 38.6270, -90.1994, 2.00, accepts_card=False)
        await db.commit()

        found = await find_corridor_stations(
            db, dallas_chicago_points, 912.0, TEST_TENANT, corridor_miles=10
        )

        assert all("no-card" not in candidate.name for candidate in found)

    async def test_mile_markers_increase_along_the_route(self, db, dallas_chicago_points):
        from app.services.geo.corridor import find_corridor_stations

        # Three stations in travel order: Oklahoma City, Springfield MO, Chicago.
        await _add_station(db, "okc", "OK", 35.4676, -97.5164, 5.40)
        await _add_station(db, "springfield", "MO", 37.2090, -93.2923, 5.30)
        await _add_station(db, "chicago", "IL", 41.8300, -87.7000, 5.60)
        await db.commit()

        found = await find_corridor_stations(
            db, dallas_chicago_points, 912.0, TEST_TENANT, corridor_miles=15
        )
        by_name = {c.name.split("— ")[-1]: c for c in found}

        assert by_name["okc"].mile_marker < by_name["springfield"].mile_marker
        assert by_name["springfield"].mile_marker < by_name["chicago"].mile_marker
        # Mile markers must be real distances along a 912 mi route, not fractions.
        assert 150 < by_name["okc"].mile_marker < 350
        assert all(0 <= c.mile_marker <= 912.0 for c in found)

    async def test_state_tax_is_attached_to_each_candidate(self, db, dallas_chicago_points):
        from app.services.geo.corridor import find_corridor_stations

        await _add_station(db, "texas-stop", "TX", 32.9000, -96.9000, 5.00)
        await db.commit()

        found = await find_corridor_stations(
            db, dallas_chicago_points, 912.0, TEST_TENANT, corridor_miles=15
        )
        texas = next(c for c in found if "texas-stop" in c.name)

        # Texas diesel tax is $0.20/gal in the seeded table.
        assert texas.tax_per_gallon == pytest.approx(0.20, abs=0.001)
        assert texas.net_price_per_gallon == pytest.approx(4.80, abs=0.001)


class TestStateSplit:
    async def test_splits_a_route_across_the_states_it_crosses(self, db, dallas_chicago_points):
        from app.services.ifta.calculator import state_mileage

        split = await state_mileage(db, dallas_chicago_points, total_miles=912.0)
        by_state = dict(split)

        # The I-35/I-44/I-55 corridor: TX -> OK -> MO -> IL, with a nick of KS/AR possible.
        assert {"TX", "OK", "MO", "IL"} <= set(by_state)
        assert sum(by_state.values()) == pytest.approx(912.0, abs=0.5)
        assert all(miles > 0 for miles in by_state.values())

    async def test_a_route_inside_one_state_gives_one_segment(self, db):
        from app.services.ifta.calculator import state_mileage

        # Dallas to Houston, entirely within Texas.
        points = _straight_line((32.7767, -96.7970), (29.7604, -95.3698))
        split = await state_mileage(db, points, total_miles=240.0)

        assert [code for code, _ in split] == ["TX"]
        assert split[0][1] == pytest.approx(240.0, abs=0.5)


class TestPlanEndpoint:
    @pytest_asyncio.fixture
    async def client(self, db, dallas_chicago_points):
        import httpx

        from app.core.db import get_session
        from app.core.deps import get_route_provider, get_tenant_id
        from app.main import app

        provider = FakeRouteProvider(dallas_chicago_points, distance_miles=912.0)

        app.dependency_overrides[get_session] = lambda: db
        app.dependency_overrides[get_tenant_id] = lambda: TEST_TENANT
        app.dependency_overrides[get_route_provider] = lambda: provider

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.dependency_overrides.clear()

    @pytest_asyncio.fixture
    async def truck(self, db):
        # 200 gal at 6.5 MPG with a 15% reserve = 1105 mi of range, so a 912 mi
        # trip needs no stop on a full tank — tests set the start level explicitly.
        profile = TruckProfile(
            tenant_id=TEST_TENANT, name="pytest truck", mpg=6.5, tank_gallons=200.0,
            reserve_fraction=0.15,
        )
        db.add(profile)
        await db.flush()
        await db.commit()
        return profile

    async def test_plans_a_trip_and_prefers_the_cheaper_stations(self, client, db, truck):
        # Cheap in Oklahoma, dear in Missouri, cheap again in Illinois.
        await _add_station(db, "okc-cheap", "OK", 35.4676, -97.5164, 4.60)
        await _add_station(db, "springfield-dear", "MO", 37.2090, -93.2923, 6.40)
        await _add_station(db, "joliet-cheap", "IL", 41.5250, -88.0817, 4.80)
        await db.commit()

        response = await client.post(
            "/api/v1/routes/plan",
            json={
                "origin": {"query": "Dallas, TX"},
                "destination": {"query": "Chicago, IL"},
                "truck_profile_id": str(truck.id),
                "start_fuel_gallons": 80,
                "ifta_mode": "pump",
                "corridor_miles": 15,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["feasible"] is True
        assert body["total_miles"] == pytest.approx(912.0, abs=1)
        assert body["candidates_considered"] >= 3
        assert body["stops"], "a 912 mi trip on 50 usable gallons must need fuel"

        bought = {stop["name"].split("— ")[-1]: stop["gallons"] for stop in body["stops"]}
        # The expensive Missouri stop must not be where the tank gets filled.
        dear = bought.get("springfield-dear", 0)
        cheap = bought.get("okc-cheap", 0) + bought.get("joliet-cheap", 0)
        assert cheap > dear

        # Tank limits hold on the real data path, not just in unit tests.
        for stop in body["stops"]:
            assert stop["departure_gallons"] <= 200.0 + 1e-6
            assert stop["arrival_gallons"] >= 30.0 - 1e-6  # the 15% reserve

        assert body["savings"]["savings_usd"] >= 0
        assert body["route_id"], "the plan should have been saved"

    async def test_per_state_mileage_sums_to_the_route_length(self, client, db, truck):
        await _add_station(db, "okc", "OK", 35.4676, -97.5164, 5.00)
        await db.commit()

        response = await client.post(
            "/api/v1/routes/plan",
            json={
                "origin": {"query": "Dallas, TX"},
                "destination": {"query": "Chicago, IL"},
                "truck_profile_id": str(truck.id),
                "corridor_miles": 15,
            },
        )
        body = response.json()
        segments = body["ifta"]["segments"]

        assert sum(s["miles"] for s in segments) == pytest.approx(body["total_miles"], abs=1.0)
        # Gallons must follow miles at the truck's MPG, not the other way round.
        for segment in segments:
            assert segment["gallons"] == pytest.approx(segment["miles"] / 6.5, abs=0.2)

    async def test_ifta_net_mode_can_change_the_chosen_station(self, client, db, truck):
        """Oklahoma at $0.20/gal tax versus Illinois at $0.628/gal.

        Pump prices: OK 5.00, IL 5.30 — Oklahoma looks cheaper.
        Net prices:  OK 4.80, IL 4.672 — Illinois is actually cheaper.
        """
        await _add_station(db, "okc", "OK", 35.4676, -97.5164, 5.00)
        await _add_station(db, "joliet", "IL", 41.5250, -88.0817, 5.30)
        await db.commit()

        payload = {
            "origin": {"query": "Dallas, TX"},
            "destination": {"query": "Chicago, IL"},
            "truck_profile_id": str(truck.id),
            "start_fuel_gallons": 80,
            "corridor_miles": 15,
            # Price the driver's time at zero, so this test sees the tax effect
            # alone rather than the stop-consolidation rule on top of it.
            "stop_overhead_usd": 0,
        }
        pump = (
            await client.post("/api/v1/routes/plan", json={**payload, "ifta_mode": "pump"})
        ).json()
        net = (
            await client.post("/api/v1/routes/plan", json={**payload, "ifta_mode": "net"})
        ).json()

        def gallons(body, name):
            return sum(s["gallons"] for s in body["stops"] if name in s["name"])

        assert gallons(pump, "okc") > gallons(net, "okc"), (
            "the net basis should shift volume away from low-tax Oklahoma"
        )
        assert gallons(net, "joliet") > gallons(pump, "joliet")

    async def test_history_round_trip(self, client, db, truck):
        await _add_station(db, "okc", "OK", 35.4676, -97.5164, 5.00)
        await db.commit()

        created = (
            await client.post(
                "/api/v1/routes/plan",
                json={
                    "origin": {"query": "Dallas, TX"},
                    "destination": {"query": "Chicago, IL"},
                    "truck_profile_id": str(truck.id),
                    "start_fuel_gallons": 80,
                    "corridor_miles": 15,
                },
            )
        ).json()

        listing = (await client.get("/api/v1/routes")).json()
        assert any(item["id"] == created["route_id"] for item in listing)

        detail = (await client.get(f"/api/v1/routes/{created['route_id']}")).json()
        assert detail["total_miles"] == pytest.approx(created["total_miles"], abs=0.1)
        assert detail["savings_usd"] == pytest.approx(created["savings"]["savings_usd"], abs=0.01)
        assert len(detail["stops"]) == len(created["stops"])
        # Stored geometry must be drawable: GeoJSON [lon, lat] inside the US.
        first_lon, first_lat = detail["geometry"]["coordinates"][0]
        assert -125 < first_lon < -66 and 24 < first_lat < 50
        assert detail["state_segments"]

    async def test_reroute_plans_from_the_current_position(self, client, db, truck):
        await _add_station(db, "okc", "OK", 35.4676, -97.5164, 5.00)
        await db.commit()

        original = (
            await client.post(
                "/api/v1/routes/plan",
                json={
                    "origin": {"query": "Dallas, TX"},
                    "destination": {"query": "Chicago, IL"},
                    "truck_profile_id": str(truck.id),
                    "corridor_miles": 15,
                },
            )
        ).json()

        response = await client.post(
            f"/api/v1/routes/{original['route_id']}/reroute",
            json={
                "current_position": {"lat": 37.2090, "lon": -93.2923, "label": "Springfield, MO"},
                "current_fuel_gallons": 60,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["origin_label"] == "Springfield, MO"
        assert body["destination_label"] == original["destination_label"]
        assert body["route_id"] != original["route_id"]

    async def test_missing_truck_profile_is_a_clear_404(self, client):
        response = await client.post(
            "/api/v1/routes/plan",
            json={
                "origin": {"query": "Dallas, TX"},
                "destination": {"query": "Chicago, IL"},
                "truck_profile_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 404
        assert "truck profile" in response.json()["detail"].lower()

    async def test_unknown_place_is_reported_not_guessed(self, client, truck):
        response = await client.post(
            "/api/v1/routes/plan",
            json={
                "origin": {"query": "Nowhere at all, ZZ"},
                "destination": {"query": "Chicago, IL"},
                "truck_profile_id": str(truck.id),
            },
        )
        assert response.status_code == 422
        assert "Nowhere at all" in response.json()["detail"]

    async def test_no_stations_yields_a_warning_not_a_crash(self, client, truck):
        response = await client.post(
            "/api/v1/routes/plan",
            json={
                "origin": {"query": "Dallas, TX"},
                "destination": {"query": "Chicago, IL"},
                "truck_profile_id": str(truck.id),
                "start_fuel_gallons": 20,
                "corridor_miles": 1,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["feasible"] is False
        assert body["warnings"]
        assert body["stops"] == []

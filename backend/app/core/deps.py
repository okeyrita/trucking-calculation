"""FastAPI dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models import DEFAULT_TENANT_ID, TruckProfile
from app.services.routing.base import RouteProvider, RoutingError, Waypoint
from app.services.routing.graphhopper import GraphHopperRouteProvider

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_tenant_id() -> uuid.UUID:
    """The tenant this request acts for.

    The MVP runs single-tenant, so this is a constant. It is a dependency rather
    than a hardcoded constant at the call sites because that is what makes the
    multitenant step a change here plus an auth dependency, and nothing else.
    """
    return DEFAULT_TENANT_ID


TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_route_provider(settings: SettingsDep) -> RouteProvider:
    return GraphHopperRouteProvider(settings=settings)


RouteProviderDep = Annotated[RouteProvider, Depends(get_route_provider)]


async def resolve_truck(
    session: AsyncSession, tenant_id: uuid.UUID, truck_profile_id: uuid.UUID | None
) -> TruckProfile:
    """The requested truck profile, or the tenant's first one."""
    query = select(TruckProfile).where(TruckProfile.tenant_id == tenant_id)
    if truck_profile_id is not None:
        query = query.where(TruckProfile.id == truck_profile_id)
    else:
        query = query.order_by(TruckProfile.created_at).limit(1)

    truck = (await session.execute(query)).scalars().first()
    if truck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No truck profile found. Create one via POST /api/v1/trucks, or run "
                "`python -m app.cli seed` to load the defaults."
            ),
        )
    return truck


async def resolve_location(provider: RouteProvider, location) -> Waypoint:
    """Turn a LocationIn into a concrete point, geocoding only when needed."""
    if location.lat is not None and location.lon is not None:
        return Waypoint(
            lat=location.lat,
            lon=location.lon,
            label=location.label or location.query or f"{location.lat:.4f},{location.lon:.4f}",
        )

    try:
        hits = await provider.geocode(location.query, limit=1)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if not hits:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Could not find a place matching {location.query!r}",
        )
    hit = hits[0]
    return Waypoint(lat=hit.lat, lon=hit.lon, label=location.label or hit.label)

"""Place lookup, so the UI can accept 'Dallas, TX' instead of coordinates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import RouteProviderDep
from app.schemas.route import GeocodeResult
from app.services.routing.base import RoutingError

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("", response_model=list[GeocodeResult])
async def geocode(
    provider: RouteProviderDep,
    q: str = Query(min_length=2, description="place name, address or 'City, ST'"),
    limit: int = Query(default=5, ge=1, le=10),
):
    try:
        hits = await provider.geocode(q, limit=limit)
    except RoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [GeocodeResult(label=hit.label, lat=hit.lat, lon=hit.lon) for hit in hits]

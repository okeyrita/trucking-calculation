"""Liveness and configuration visibility."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: SessionDep) -> dict:
    """Reports what the deployment is actually configured to do.

    Deliberately includes whether the truck profile and contract prices are
    available: both silently degrade the quality of the answer, and someone
    looking at a suspicious number needs to see it here first.
    """
    settings = get_settings()
    checks: dict[str, object] = {}

    try:
        await session.execute(text("SELECT 1"))
        postgis = (await session.execute(text("SELECT PostGIS_Version()"))).scalar()
        checks["database"] = "ok"
        checks["postgis"] = postgis
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        checks["database"] = f"error: {exc}"[:200]

    return {
        "status": "ok" if checks.get("database") == "ok" else "degraded",
        "checks": checks,
        "routing": {
            "provider": "graphhopper",
            "api_key_configured": bool(settings.graphhopper_api_key),
            "truck_profile_requested": settings.routing_truck_profile_enabled,
        },
        "fuel_prices": {
            "provider": settings.fuel_price_provider,
            "contract_prices": settings.fuel_price_provider == "contract_portal",
        },
    }

"""Station lookup for the map."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.core.deps import SessionDep, TenantDep
from app.schemas.route import StationOut

router = APIRouter(prefix="/stations", tags=["stations"])

# Clauses are assembled rather than written once with nullable parameters on
# purpose: asyncpg infers parameter types from context, and a NULL handed to
# ST_MakeEnvelope has no inferable type, which fails the whole query.
_BASE_SQL = """
WITH latest_price AS (
    SELECT DISTINCT ON (station_id) station_id, price_per_gallon, effective_date
    FROM fuel_prices
    WHERE fuel_type = :fuel_type AND effective_date <= :as_of
    ORDER BY station_id, effective_date DESC
)
SELECT s.id, s.name, s.brand, s.state, ST_Y(s.geom) AS lat, ST_X(s.geom) AS lon,
       s.accepts_card, lp.price_per_gallon, lp.effective_date
FROM fuel_stations s
LEFT JOIN latest_price lp ON lp.station_id = s.id
WHERE s.tenant_id = :tenant_id
"""

_ORDER_SQL = """
ORDER BY s.state, s.name
LIMIT :limit
"""


@router.get("", response_model=list[StationOut])
async def list_stations(
    session: SessionDep,
    tenant_id: TenantDep,
    bbox: str | None = Query(
        default=None, description="min_lon,min_lat,max_lon,max_lat — for map viewports"
    ),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    accepts_card: bool = Query(default=True, description="only card-accepting stations"),
    fuel_type: str = "diesel",
    limit: int = Query(default=500, ge=1, le=5000),
):
    clauses: list[str] = []
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        "fuel_type": fuel_type,
        "as_of": date.today(),
        "limit": limit,
    }

    if state:
        clauses.append("AND s.state = :state")
        params["state"] = state.upper()
    if accepts_card:
        clauses.append("AND s.accepts_card")
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(part) for part in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(422, "bbox must be min_lon,min_lat,max_lon,max_lat") from exc
        clauses.append(
            "AND s.geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)"
        )
        params.update(
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat}
        )

    sql = text(_BASE_SQL + "\n".join(clauses) + _ORDER_SQL)
    rows = (await session.execute(sql, params)).mappings()

    return [
        StationOut(
            id=row["id"],
            name=row["name"],
            brand=row["brand"],
            state=row["state"],
            lat=row["lat"],
            lon=row["lon"],
            accepts_card=row["accepts_card"],
            price_per_gallon=(
                float(row["price_per_gallon"]) if row["price_per_gallon"] is not None else None
            ),
            price_date=row["effective_date"].isoformat() if row["effective_date"] else None,
        )
        for row in rows
    ]

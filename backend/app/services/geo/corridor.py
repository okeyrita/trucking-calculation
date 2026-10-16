"""Find the card-accepting stations that lie along a route.

Two spatial questions are answered in one query:

* *Is this station on my way?* — ``ST_DWithin`` against the route, in meters.
* *How far along am I when I reach it?* — ``ST_LineLocatePoint``, which returns a
  fraction of the line's length that is multiplied by the provider's road mileage.

Both are done in EPSG:5070 (Albers equal-area for the US) rather than in raw
lon/lat degrees. In degrees a mile of longitude is shorter than a mile of latitude
everywhere but the equator, so a diagonal route like Dallas->Chicago would get mile
markers several percent off — enough to matter when the plan says a station is just
within range.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.geo.simplify import linestring_wkt, simplify
from app.services.optimizer.fuel_plan import StationCandidate

METERS_PER_MILE = 1609.344
# Degrees of latitude per mile, used only to pad the bounding-box prefilter.
_DEG_PER_MILE = 1.0 / 69.0

_CORRIDOR_SQL = text(
    """
WITH route AS (
    SELECT ST_GeomFromText(:wkt, 4326) AS g,
           ST_Transform(ST_GeomFromText(:wkt, 4326), 5070) AS g_m
),
latest_price AS (
    SELECT DISTINCT ON (station_id)
           station_id, price_per_gallon, is_contract_price, effective_date
    FROM fuel_prices
    WHERE fuel_type = :fuel_type AND effective_date <= :as_of
    ORDER BY station_id, effective_date DESC
)
SELECT s.id::text            AS station_id,
       s.name                AS name,
       s.brand               AS brand,
       s.state               AS state,
       ST_Y(s.geom)          AS lat,
       ST_X(s.geom)          AS lon,
       ST_LineLocatePoint(route.g_m, ST_Transform(s.geom, 5070)) AS frac,
       ST_Distance(ST_Transform(s.geom, 5070), route.g_m) / :meters_per_mile AS off_route_miles,
       lp.price_per_gallon   AS price_per_gallon,
       lp.effective_date     AS price_date,
       COALESCE(rate.tax_per_gallon, 0) AS tax_per_gallon
FROM fuel_stations s
JOIN route          ON s.geom && ST_Expand(route.g, :bbox_degrees)
JOIN latest_price lp ON lp.station_id = s.id
LEFT JOIN LATERAL (
    SELECT tax_per_gallon
    FROM ifta_rates
    WHERE state_code = s.state AND fuel_type = :fuel_type AND effective_from <= :as_of
    ORDER BY effective_from DESC
    LIMIT 1
) rate ON TRUE
WHERE s.tenant_id = :tenant_id
  AND s.accepts_card
  AND ST_DWithin(s.geom::geography, route.g::geography, :corridor_meters)
ORDER BY frac
"""
)


async def find_corridor_stations(
    session: AsyncSession,
    route_points: list[tuple[float, float]],
    total_miles: float,
    tenant_id: uuid.UUID,
    corridor_miles: float = 3.0,
    fuel_type: str = "diesel",
    as_of: date | None = None,
    simplify_tolerance_meters: float = 200.0,
) -> list[StationCandidate]:
    """Stations within ``corridor_miles`` of the route, ordered by mile marker.

    Stations with no known price are excluded by the join: routing a driver to a
    pump whose price we cannot see defeats the purpose.
    """
    if len(route_points) < 2:
        return []

    wkt = linestring_wkt(simplify(route_points, simplify_tolerance_meters))
    rows = (
        await session.execute(
            _CORRIDOR_SQL,
            {
                "wkt": wkt,
                "fuel_type": fuel_type,
                "as_of": as_of or date.today(),
                "tenant_id": tenant_id,
                "corridor_meters": corridor_miles * METERS_PER_MILE,
                "bbox_degrees": corridor_miles * _DEG_PER_MILE * 1.5,
                "meters_per_mile": METERS_PER_MILE,
            },
        )
    ).mappings()

    candidates: list[StationCandidate] = []
    for row in rows:
        label = row["name"]
        if row["brand"] and row["brand"] not in label:
            label = f"{row['brand']} — {label}"
        candidates.append(
            StationCandidate(
                station_id=row["station_id"],
                name=label,
                state=row["state"],
                mile_marker=float(row["frac"]) * total_miles,
                price_per_gallon=float(row["price_per_gallon"]),
                tax_per_gallon=float(row["tax_per_gallon"]),
                # Off-route distance is paid twice: out to the pump and back.
                detour_miles=float(row["off_route_miles"]) * 2.0,
                lat=float(row["lat"]),
                lon=float(row["lon"]),
            )
        )
    return candidates

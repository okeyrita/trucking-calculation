"""Polyline simplification and WKT assembly.

A cross-country GraphHopper route is tens of thousands of vertices. Sending all of
them to PostGIS on every corridor query is wasteful, and the extra detail buys
nothing when the corridor is measured in miles. Douglas-Peucker at a ~200 m
tolerance cuts the vertex count by an order of magnitude while leaving the line
well inside the corridor it is used to build.

Implemented here rather than pulled from Shapely so the geometry helpers stay
importable (and unit-testable) without a compiled GEOS dependency.
"""

from __future__ import annotations

# Degrees of latitude per meter — good enough as a tolerance unit, since the
# tolerance only needs to be the right order of magnitude.
_DEG_PER_METER = 1.0 / 111_320.0


def _perpendicular_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    (y, x), (y1, x1), (y2, x2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2) ** 0.5


def simplify(
    points: list[tuple[float, float]], tolerance_meters: float = 200.0
) -> list[tuple[float, float]]:
    """Douglas-Peucker on ``[(lat, lon), ...]``; endpoints are always kept."""
    if len(points) < 3 or tolerance_meters <= 0:
        return list(points)

    tolerance = tolerance_meters * _DEG_PER_METER
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst = 0.0
        index = first
        for i in range(first + 1, last):
            distance = _perpendicular_distance(points[i], points[first], points[last])
            if distance > worst:
                worst, index = distance, i
        if worst > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))

    return [p for p, k in zip(points, keep, strict=True) if k]


def linestring_wkt(points: list[tuple[float, float]]) -> str:
    """``[(lat, lon), ...]`` -> ``LINESTRING(lon lat, ...)``.

    WKT is x-then-y, i.e. longitude first. Getting this backwards is the classic
    way to end up with routes off the coast of Africa.
    """
    if len(points) < 2:
        raise ValueError("a LINESTRING needs at least two points")
    body = ", ".join(f"{lon:.6f} {lat:.6f}" for lat, lon in points)
    return f"LINESTRING({body})"


def point_wkt(lat: float, lon: float) -> str:
    return f"POINT({lon:.6f} {lat:.6f})"

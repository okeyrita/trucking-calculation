"""Google/GraphHopper encoded-polyline codec.

GraphHopper returns route geometry in this format by default; a cross-country US
route is tens of thousands of points, and encoded it is roughly a tenth the size.
"""

from __future__ import annotations


def decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode to ``[(lat, lon), ...]``."""
    coords: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    factor = float(10**precision)
    length = len(encoded)

    while index < length:
        deltas = []
        for _ in range(2):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    raise ValueError("truncated polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))

    return coords


def encode_polyline(coords: list[tuple[float, float]], precision: int = 5) -> str:
    """Encode ``[(lat, lon), ...]``. Used only by tests and fixtures."""
    factor = 10**precision
    out: list[str] = []
    prev_lat = 0
    prev_lon = 0

    for lat, lon in coords:
        ilat = round(lat * factor)
        ilon = round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = ilat, ilon

    return "".join(out)

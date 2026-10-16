"""Regional diesel prices and the per-station spread.

Read this before trusting any price the MVP shows.

The *regional* level is real: EIA publishes on-highway diesel averages per PADD
region weekly, in the public domain, and that is the difference the product is
built to exploit — a truck crossing from the Gulf Coast into California drives
through a genuine ~$1.50/gal swing.

The *per-station* level is modelled, not measured. Until the fuel-card portal is
connected, we do not know what any individual pump charges this company, so each
station gets a deterministic offset derived from its id. That keeps the demo
plausible and the tests reproducible, and it is why every price this module
produces is stored with ``is_contract_price=False``.
"""

from __future__ import annotations

import hashlib

# EIA on-highway diesel averages, USD/gal, snapshot of 2026-08-24.
# https://www.eia.gov/petroleum/gasdiesel/ — refreshed live by the EIA provider.
PADD_SNAPSHOT: dict[str, float] = {
    "PADD1A": 5.716,  # New England
    "PADD1B": 5.840,  # Central Atlantic
    "PADD1C": 5.350,  # Lower Atlantic
    "PADD2": 5.636,  # Midwest
    "PADD3": 5.481,  # Gulf Coast
    "PADD4": 5.537,  # Rocky Mountain
    "PADD5": 5.859,  # West Coast excluding California
    "CA": 7.040,  # California, published separately because it is such an outlier
}

STATE_TO_REGION: dict[str, str] = {
    # New England
    **{s: "PADD1A" for s in ("CT", "ME", "MA", "NH", "RI", "VT")},
    # Central Atlantic
    **{s: "PADD1B" for s in ("DE", "DC", "MD", "NJ", "NY", "PA")},
    # Lower Atlantic
    **{s: "PADD1C" for s in ("FL", "GA", "NC", "SC", "VA", "WV")},
    # Midwest
    **{
        s: "PADD2"
        for s in (
            "IL", "IN", "IA", "KS", "KY", "MI", "MN", "MO",
            "NE", "ND", "OH", "OK", "SD", "TN", "WI",
        )
    },
    # Gulf Coast
    **{s: "PADD3" for s in ("AL", "AR", "LA", "MS", "NM", "TX")},
    # Rocky Mountain
    **{s: "PADD4" for s in ("CO", "ID", "MT", "UT", "WY")},
    # West Coast
    **{s: "PADD5" for s in ("AK", "AZ", "HI", "NV", "OR", "WA")},
    "CA": "CA",
}

_NATIONAL_FALLBACK = 5.652  # EIA US average from the same snapshot

# Real truck stops vary by roughly this much around their regional average.
_STATION_SPREAD_USD = 0.15


def region_for_state(state: str) -> str:
    return STATE_TO_REGION.get(state.upper(), "PADD2")


def regional_price(state: str, regional: dict[str, float] | None = None) -> float:
    table = regional or PADD_SNAPSHOT
    return table.get(region_for_state(state), table.get("PADD2", _NATIONAL_FALLBACK))


def station_offset(external_id: str, spread: float = _STATION_SPREAD_USD) -> float:
    """A stable pseudo-random offset in ``[-spread, +spread]`` for one station.

    Derived from the id alone, so the same station gets the same offset on every
    run: prices stay stable across refreshes and tests stay deterministic.
    """
    digest = hashlib.sha256(external_id.encode("utf-8")).digest()
    unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF  # 0..1
    return round((unit * 2.0 - 1.0) * spread, 3)


def modelled_price(
    external_id: str, state: str, regional: dict[str, float] | None = None
) -> float:
    """Regional average (real) plus a per-station offset (modelled)."""
    return round(max(0.50, regional_price(state, regional) + station_offset(external_id)), 3)

"""IFTA rate reference."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import SessionDep

router = APIRouter(prefix="/ifta", tags=["ifta"])

_SQL = text(
    """
SELECT DISTINCT ON (state_code) state_code, tax_per_gallon, effective_from
FROM ifta_rates
WHERE fuel_type = :fuel_type AND effective_from <= :as_of
ORDER BY state_code, effective_from DESC
"""
)


@router.get("/rates")
async def list_rates(session: SessionDep, fuel_type: str = "diesel") -> dict:
    """Current fuel-tax rate per state, in USD per gallon.

    The ``disclaimer`` is part of the payload on purpose: these rates are seeded
    placeholders until someone loads the quarterly IFTA matrix, and any UI showing
    them should say so.
    """
    rows = (
        await session.execute(_SQL, {"fuel_type": fuel_type, "as_of": date.today()})
    ).mappings()
    rates = [
        {
            "state_code": row["state_code"],
            "tax_per_gallon": float(row["tax_per_gallon"]),
            "effective_from": row["effective_from"].isoformat(),
        }
        for row in rows
    ]
    return {
        "fuel_type": fuel_type,
        "count": len(rates),
        "rates": rates,
        "disclaimer": (
            "Seeded approximate rates. Verify against the quarterly IFTA Inc. tax "
            "matrix (https://www.iftach.org/) before using for filing or billing."
        ),
    }

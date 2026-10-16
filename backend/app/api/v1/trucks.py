"""Truck profile CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import SessionDep, TenantDep, resolve_truck
from app.models import TruckProfile
from app.schemas.truck import TruckProfileIn, TruckProfileOut, TruckProfileUpdate

router = APIRouter(prefix="/trucks", tags=["trucks"])


def _to_out(truck: TruckProfile) -> TruckProfileOut:
    return TruckProfileOut(
        id=truck.id,
        name=truck.name,
        mpg=truck.mpg,
        tank_gallons=truck.tank_gallons,
        reserve_fraction=truck.reserve_fraction,
        height_m=truck.height_m,
        width_m=truck.width_m,
        length_m=truck.length_m,
        weight_kg=truck.weight_kg,
        axles=truck.axles,
        usable_gallons=round(truck.usable_gallons, 2),
        range_miles=round(truck.range_miles, 1),
    )


@router.get("", response_model=list[TruckProfileOut])
async def list_trucks(session: SessionDep, tenant_id: TenantDep):
    rows = (
        await session.execute(
            select(TruckProfile)
            .where(TruckProfile.tenant_id == tenant_id)
            .order_by(TruckProfile.created_at)
        )
    ).scalars()
    return [_to_out(truck) for truck in rows]


@router.post("", response_model=TruckProfileOut, status_code=status.HTTP_201_CREATED)
async def create_truck(payload: TruckProfileIn, session: SessionDep, tenant_id: TenantDep):
    truck = TruckProfile(tenant_id=tenant_id, **payload.model_dump())
    session.add(truck)
    await session.flush()
    return _to_out(truck)


@router.get("/{truck_id}", response_model=TruckProfileOut)
async def get_truck(truck_id: uuid.UUID, session: SessionDep, tenant_id: TenantDep):
    return _to_out(await resolve_truck(session, tenant_id, truck_id))


@router.patch("/{truck_id}", response_model=TruckProfileOut)
async def update_truck(
    truck_id: uuid.UUID, payload: TruckProfileUpdate, session: SessionDep, tenant_id: TenantDep
):
    truck = await resolve_truck(session, tenant_id, truck_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(truck, field, value)
    await session.flush()
    return _to_out(truck)


@router.delete("/{truck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_truck(truck_id: uuid.UUID, session: SessionDep, tenant_id: TenantDep):
    truck = await resolve_truck(session, tenant_id, truck_id)
    try:
        await session.delete(truck)
        await session.flush()
    except Exception as exc:  # noqa: BLE001 - surfaced as a clear 409 below
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This truck profile is referenced by saved routes and cannot be deleted.",
        ) from exc

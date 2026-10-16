"""API v1 router assembly."""

from fastapi import APIRouter

from app.api.v1 import geocode, health, ifta, routes, stations, trucks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(routes.router)
api_router.include_router(trucks.router)
api_router.include_router(stations.router)
api_router.include_router(ifta.router)
api_router.include_router(geocode.router)

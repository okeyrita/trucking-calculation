"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

DESCRIPTION = """
Truck-friendly routing with fuel-cost optimization for US long-haul (Class 8).

Give it an origin and a destination and it returns a truck-legal route plus the
cheapest way to fuel it: which card-accepting stations to use, how many gallons to
buy at each, and how much that beats fuelling without guidance.

Units are US customary: miles, gallons, and MPG (miles per gallon, the inverse of
L/100km). `ifta_mode` switches the optimization between the price on the stele
(`pump`) and the price after the state's IFTA fuel-tax credit (`net`).
"""

app = FastAPI(
    title="Trucking — Routing & Fuel Control",
    description=DESCRIPTION,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
)

# The SPA is served from a different origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "trucking-fuel-routing",
        "docs": "/docs",
        "health": "/api/v1/health",
    }

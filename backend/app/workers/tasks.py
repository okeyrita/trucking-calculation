"""Background tasks."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import DEFAULT_TENANT_ID
from app.services.fuel.refresh import refresh_fuel_data
from app.services.fuel.registry import build_fuel_provider
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _refresh(provider_name: str | None) -> dict:
    settings = get_settings()
    name = provider_name or settings.fuel_price_provider

    async with session_scope() as session:
        from app.scrapers.session import STATUS_NEEDS_LOGIN, STATUS_OK, ScraperSessionStore

        store = ScraperSessionStore(session)
        storage_state = None
        if name == "contract_portal":
            storage_state = await store.load_storage_state(name)

        provider = build_fuel_provider(name, settings, storage_state)
        report = await refresh_fuel_data(session, provider, DEFAULT_TENANT_ID)

        # An expired portal session is an operational fact to record, not a crash
        # to retry: a human has to log in again before this can succeed.
        if name == "contract_portal":
            await store.mark(
                name,
                STATUS_NEEDS_LOGIN if report.status == "needs_login" else STATUS_OK,
                report.message,
            )

        await session.commit()

    return {
        "provider": report.provider,
        "status": report.status,
        "stations": report.stations,
        "prices": report.prices,
        "message": report.message,
    }


@celery_app.task(
    name="app.workers.tasks.refresh_fuel_prices",
    bind=True,
    max_retries=3,
    default_retry_delay=600,
)
def refresh_fuel_prices(self, provider: str | None = None) -> dict:
    """Fetch today's prices. Retries transient errors; never retries needs_login."""
    result = asyncio.run(_refresh(provider))

    if result["status"] == "error":
        logger.error("fuel refresh error: %s", result["message"])
        raise self.retry(exc=RuntimeError(result["message"]))
    if result["status"] == "needs_login":
        logger.warning("fuel refresh blocked, manual login required: %s", result["message"])

    return result

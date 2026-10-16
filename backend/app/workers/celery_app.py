"""Celery application and schedule.

Only one recurring job matters for the MVP: pull fuel prices once a day, because
that is how often US fuel prices change. Everything else the API does is
synchronous request work.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "trucking",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=50,  # Playwright leaks; recycle workers
    timezone="UTC",
    beat_schedule={
        "refresh-fuel-prices-daily": {
            "task": "app.workers.tasks.refresh_fuel_prices",
            "schedule": crontab(hour=settings.fuel_price_refresh_cron_hour, minute=15),
        },
    },
)

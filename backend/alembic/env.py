"""Alembic environment, wired to the async engine and the app's settings."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.db import Base

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS brings a lot of its own furniture: spatial_ref_sys, the topology tables
# and the whole tiger geocoder schema. Autogenerate would happily propose dropping
# all of it, so Alembic is limited to the tables this application declares.
def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    # GeoAlchemy2 creates spatial indexes itself; they are declared explicitly on
    # the models, so anything else index-shaped that is reflected is not ours.
    if type_ == "index" and name and name.startswith("idx_") and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

"""Alembic env: URL desde settings (DATABASE_URL) + metadata de modelos."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importar modelos para que registren sus tablas en Base.metadata.
import livepulse.modules.broadcasts.models  # noqa: F401
import livepulse.modules.shifts.models  # noqa: F401
import livepulse.shared.idempotency  # noqa: F401
from livepulse.shared.config import settings
from livepulse.shared.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata,
                      literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": settings.database_url}, prefix="sqlalchemy.")
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

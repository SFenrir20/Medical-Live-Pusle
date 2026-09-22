"""Real PostgreSQL connectivity, enabled in CI through DATABASE_URL."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="PostgreSQL URL not configured")
async def test_postgres_connection_and_transaction():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
            await connection.execute(text("CREATE TEMP TABLE ci_probe (value integer)"))
            await connection.execute(text("INSERT INTO ci_probe VALUES (42)"))
            assert await connection.scalar(text("SELECT value FROM ci_probe")) == 42
    finally:
        await engine.dispose()

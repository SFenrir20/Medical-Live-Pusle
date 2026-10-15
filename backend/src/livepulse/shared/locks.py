"""Transaction-scoped locks for capture and contact deduplication."""
import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def lock(session: AsyncSession, value: str):
    # Serialize inserts even before there is a row to lock.
    key = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

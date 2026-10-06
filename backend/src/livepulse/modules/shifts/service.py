"""Atomic attendance transitions, independent of monitoring."""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...shared.idempotency import IdempotencyKey
from .models import Shift


def require_account(account_id: str, user: dict):
    if account_id not in user.get("accounts", []):
        raise HTTPException(status_code=403, detail="Cuenta no autorizada")


def serialize(shift: Shift):
    return {key: (getattr(shift, key).isoformat() if getattr(shift, key) else None)
            if key in ("started_at", "ended_at") else getattr(shift, key)
            for key in ("id", "account_id", "user_id", "started_at", "ended_at",
                        "end_reason", "closed_by")}


async def active_shift(session: AsyncSession, account_id: str, user: dict):
    require_account(account_id, user)
    shift = await session.scalar(select(Shift).where(
        Shift.account_id == account_id, Shift.ended_at.is_(None)))
    return serialize(shift) if shift else None


async def history(session: AsyncSession, user: dict, limit: int, offset: int):
    rows = (await session.scalars(select(Shift).where(Shift.user_id == user["id"])
            .order_by(Shift.started_at.desc(), Shift.id.desc()).offset(offset)
            .limit(limit + 1))).all()
    return {"items": [serialize(row) for row in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None}


async def lock(session: AsyncSession, value: str):
    # Also serialize inserts when there is no active row to lock yet.
    key = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def mark(*, session: AsyncSession, account_id: str, user: dict,
               idempotency_key: str, operation: str, expected_id: str | None):
    require_account(account_id, user)
    request = {"operation": operation, "account_id": account_id, "expected_id": expected_id}
    key = hashlib.sha256(json.dumps([user["id"], idempotency_key]).encode()).hexdigest()
    async with session.begin():
        await lock(session, "request:" + key)
        previous = await session.get(IdempotencyKey, key)
        if previous:
            saved = json.loads(previous.response)
            if saved["request"] != request:
                raise HTTPException(409, "La clave de reintento pertenece a otra operación.")
            return saved["result"]
        await lock(session, "account:" + account_id)
        active = await session.scalar(select(Shift).where(
            Shift.account_id == account_id, Shift.ended_at.is_(None)).with_for_update())
        now = await session.scalar(select(func.clock_timestamp()))
        if operation == "check-in":
            if active and active.user_id == user["id"]:
                result = serialize(active)
            else:
                if (active.id if active else None) != expected_id:
                    raise HTTPException(409, "El turno cambió. Actualiza antes de marcar o relevar.")
                if active:
                    active.ended_at = now
                    active.end_reason = "handover"
                    active.closed_by = user["id"]
                    await session.flush()
                shift = Shift(id=str(uuid4()), account_id=account_id, user_id=user["id"],
                              started_at=now)
                session.add(shift)
                result = serialize(shift)
        else:
            if not active or active.id != expected_id:
                raise HTTPException(409, "Ese turno ya terminó o fue relevado. Actualiza el estado.")
            if active.user_id != user["id"]:
                raise HTTPException(403, "Solo puedes marcar la salida de tu propio turno.")
            active.ended_at = now
            active.end_reason = "manual"
            active.closed_by = user["id"]
            result = serialize(active)
        session.add(IdempotencyKey(key=key, scope=operation,
                    response=json.dumps({"request": request, "result": result})))
    return result

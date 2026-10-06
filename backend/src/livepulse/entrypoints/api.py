from fastapi import Depends, FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..modules.shifts import service
from ..shared.auth import get_current_user
from ..shared.config import settings
from ..shared.db import get_session

app = FastAPI(title="LivePulse API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])


@app.get("/v1/me")
def me(user=Depends(get_current_user)):
    return user


class CheckInBody(BaseModel):
    account_id: str = Field(min_length=1, max_length=32)
    replace_shift_id: str | None = Field(default=None, min_length=1, max_length=36)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/v1/shifts/active")
async def active_shift(account_id: str, user=Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    return await service.active_shift(session, account_id, user)


@app.get("/v1/shifts/history")
async def history(limit: int = Query(default=20, ge=1, le=100),
                  offset: int = Query(default=0, ge=0), user=Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)):
    return await service.history(session, user, limit, offset)


@app.post("/v1/shifts/check-in", status_code=201)
async def api_check_in(
    body: CheckInBody,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    user=Depends(get_current_user), session: AsyncSession = Depends(get_session),
):
    return await service.mark(session=session, account_id=body.account_id, user=user,
                              idempotency_key=idempotency_key, operation="check-in",
                              expected_id=body.replace_shift_id)


@app.post("/v1/shifts/check-out")
async def api_check_out(
    account_id: str,
    shift_id: str = Query(min_length=1, max_length=36),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    user=Depends(get_current_user), session: AsyncSession = Depends(get_session),
):
    return await service.mark(session=session, account_id=account_id, user=user,
                              idempotency_key=idempotency_key, operation="check-out",
                              expected_id=shift_id)

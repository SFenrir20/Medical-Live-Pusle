from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel

from ..modules.shifts.service import check_in, check_out, require_account, unavailable
from ..shared.auth import get_current_user

app = FastAPI(title="LivePulse API", version="0.1.0")


class CheckInBody(BaseModel):
    account_id: str  # medical | medical-2, regla: 1 turno activo por cuenta
    lat: float | None = None
    lng: float | None = None


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/v1/shifts/active")
async def active_shift(account_id: str, user=Depends(get_current_user)):
    require_account(account_id, user)
    unavailable()


@app.post("/v1/shifts/check-in", status_code=201)
async def api_check_in(
    body: CheckInBody,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
):
    return await check_in(account_id=body.account_id, user=user, idempotency_key=idempotency_key)


@app.post("/v1/shifts/check-out", status_code=200)
async def api_check_out(
    account_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
):
    return await check_out(account_id=account_id, user=user, idempotency_key=idempotency_key)

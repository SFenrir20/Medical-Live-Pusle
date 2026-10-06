from fastapi.testclient import TestClient

from livepulse.entrypoints.api import app
from livepulse.shared.auth import get_current_user

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_shift_endpoints_require_auth():
    assert client.post("/v1/shifts/check-in", json={"account_id": "medical"}).status_code == 401
    assert client.get("/v1/shifts/history").status_code == 401
    assert client.get("/v1/shifts/active?account_id=medical").status_code == 401
    assert client.post("/v1/shifts/check-out?account_id=medical&shift_id=x").status_code == 401


def test_arbitrary_token_is_not_an_authenticated_user(monkeypatch):
    from livepulse.shared.config import settings
    monkeypatch.setattr(settings, "clerk_issuer", "")
    assert client.post("/v1/shifts/check-in", json={"account_id": "medical"},
                       headers={"Authorization": "Bearer invented-token"}).status_code == 503


def test_account_authorization_precedes_database_access():
    app.dependency_overrides[get_current_user] = lambda: {"id": "ana", "accounts": []}
    try:
        headers = {"Idempotency-Key": "key"}
        assert client.post("/v1/shifts/check-in", json={"account_id": "medical"},
                           headers=headers).status_code == 403
        assert client.post("/v1/shifts/check-out?account_id=medical&shift_id=x",
                           headers=headers).status_code == 403
        assert client.get("/v1/shifts/active?account_id=medical").status_code == 403
    finally:
        app.dependency_overrides.clear()

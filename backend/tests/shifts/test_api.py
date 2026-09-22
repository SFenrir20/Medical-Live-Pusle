import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from livepulse.entrypoints.api import app  # noqa: E402
from livepulse.shared.auth import get_current_user  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_check_in_requiere_auth():
    r = client.post("/v1/shifts/check-in", json={"account_id": "medical"})
    assert r.status_code in (401, 403)


def test_arbitrary_token_is_not_an_authenticated_user():
    r = client.post(
        "/v1/shifts/check-in",
        json={"account_id": "medical"},
        headers={"Authorization": "Bearer invented-token"},
    )
    assert r.status_code == 503


@pytest.mark.parametrize("account,expected", [("medical", 501), ("other", 403)])
@pytest.mark.parametrize("operation", ["check-in", "check-out", "active"])
def test_unimplemented_operations_never_confirm_a_shift(account, expected, operation):
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user",
        "accounts": ["medical"],
    }
    try:
        if operation == "check-in":
            r = client.post("/v1/shifts/check-in", json={"account_id": account})
        elif operation == "check-out":
            r = client.post("/v1/shifts/check-out", params={"account_id": account})
        else:
            r = client.get("/v1/shifts/active", params={"account_id": account})
        assert r.status_code == expected
    finally:
        app.dependency_overrides.clear()

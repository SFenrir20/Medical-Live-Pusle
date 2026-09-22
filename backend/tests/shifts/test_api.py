import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from livepulse.entrypoints.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_check_in_requiere_auth():
    r = client.post("/v1/shifts/check-in", json={"account_id": "medical"})
    assert r.status_code in (401, 403)

from time import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from livepulse.entrypoints.api import app
from livepulse.shared import auth

client = TestClient(app)


@pytest.fixture
def signing(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth.settings, "clerk_issuer", "https://clerk.example")
    monkeypatch.setattr(auth.settings, "clerk_authorized_parties", ["http://localhost:8081"])
    monkeypatch.setattr(auth.settings, "livepulse_user_accounts", {"user_approved": ["medical"]})
    provider = Mock()
    provider.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private.public_key())
    monkeypatch.setattr(auth, "jwks_client", lambda _: provider)

    def issue(**changes):
        now = int(time())
        claims = dict(sub="user_new", sid="sess_1", iss="https://clerk.example",
                      exp=now + 60, iat=now, nbf=now, azp="http://localhost:8081")
        omit = changes.pop("omit", [])
        claims.update(changes)
        for field in omit:
            claims.pop(field, None)
        return jwt.encode(claims, private, algorithm="RS256")
    return issue


def request(token, path="/v1/me"):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def test_new_user_is_pending_and_cannot_access_shifts(signing):
    token = signing(accounts=["medical"], role="admin")
    assert request(token).json() == {"id": "user_new", "accounts": [], "status": "pending"}
    assert request(token, "/v1/shifts/active?account_id=medical").status_code == 403


def test_operator_grants_only_authorized_accounts(signing):
    token = signing(sub="user_approved")
    assert request(token).json()["accounts"] == ["medical"]
    assert request(token, "/v1/shifts/active?account_id=medical-2").status_code == 403


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iss": "https://attacker.example"}, {"azp": "https://attacker.example"},
    {"nbf": 9999999999}, {"sub": ""}, {"sts": "pending"}, {"sid": ""},
])
def test_invalid_claims_rejected(signing, claims):
    assert request(signing(**claims)).status_code == 401


def test_invalid_signature_and_malformed_token(signing):
    token = signing()
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(jwt.decode(token, options={"verify_signature": False}), other,
                        algorithm="RS256")
    assert request(forged).status_code == 401
    assert request("not-a-token").status_code == 401


def test_missing_token():
    assert client.get("/v1/me").status_code == 401


@pytest.mark.parametrize("field", ["exp", "nbf", "sid", "iss"])
def test_missing_required_claim(signing, field):
    assert request(signing(omit=[field])).status_code == 401


def test_native_session_can_omit_browser_origin(signing):
    assert request(signing(omit=["azp"])).status_code == 200


def test_jwks_outage_returns_retryable_error(signing, monkeypatch):
    provider = Mock()
    provider.get_signing_key_from_jwt.side_effect = auth.PyJWKClientConnectionError("offline")
    monkeypatch.setattr(auth, "jwks_client", lambda _: provider)
    assert request(signing()).status_code == 503

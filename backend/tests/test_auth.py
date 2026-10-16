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


def test_verified_identity_without_a_clerk_role_has_none(signing):
    assert request(signing()).json() == {"id": "user_new", "role": None}


def test_role_comes_from_the_signed_session_metadata(signing):
    token = signing(metadata={"livepulse": {"role": "supervisor"}})
    assert request(token).json() == {"id": "user_new", "role": "supervisor"}
    for bad in ({"livepulse": {"role": "dios"}}, {"livepulse": {}}, {"otra": {"role": "gerente"}},
                {"role": "gerente"}, "supervisor", {"livepulse": "gerente"}):
        assert request(signing(metadata=bad)).json()["role"] is None, bad
    # Claims users could edit themselves are never read.
    assert request(signing(unsafe_metadata={"livepulse": {"role": "supervisor"}})).json()["role"] is None


def test_backend_api_fallback_only_when_the_token_has_no_metadata_claim(signing, monkeypatch):
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append((url, headers))
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"public_metadata": {"livepulse": {"role": "gerente"}}})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    monkeypatch.setattr(auth, "_directory", {})
    # No secret configured: nothing is guessed.
    assert request(signing()).json()["role"] is None and calls == []
    monkeypatch.setattr(auth.settings, "clerk_secret_key", "sk_test_x")
    assert request(signing()).json()["role"] == "gerente"
    assert request(signing()).json()["role"] == "gerente"
    assert len(calls) == 1  # cached for a short time
    assert calls[0][0] == "https://api.clerk.com/v1/users/user_new"
    assert calls[0][1] == {"Authorization": "Bearer sk_test_x"}
    # A token that carries the claim is trusted as is: no extra call.
    assert request(signing(metadata={"livepulse": {"role": "supervisor"}})).json()["role"] == "supervisor"
    assert len(calls) == 1


def test_backend_api_outage_is_retryable_not_a_silent_denial(signing, monkeypatch):
    def broken(url, timeout=None, headers=None):
        raise auth.httpx.ConnectError("offline")

    monkeypatch.setattr(auth.httpx, "get", broken)
    monkeypatch.setattr(auth, "_directory", {})
    monkeypatch.setattr(auth.settings, "clerk_secret_key", "sk_test_x")
    assert request(signing()).status_code == 503


@pytest.mark.parametrize("path,method", [
    ("/v1/shifts/active?account_id=medical", "GET"),
    ("/v1/shifts/history", "GET"),
    ("/v1/shifts/check-in", "POST"),
    ("/v1/shifts/check-out", "POST"),
    ("/v1/analytics/lives/1/attribution", "GET"),
])
def test_retired_attendance_routes_are_unavailable(signing, path, method):
    response = client.request(method, path, headers={"Authorization": f"Bearer {signing()}"})
    assert response.status_code == 404


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


def test_session_without_optional_origin(signing):
    assert request(signing(omit=["azp"])).status_code == 200


def test_jwks_outage_returns_retryable_error(signing, monkeypatch):
    provider = Mock()
    provider.get_signing_key_from_jwt.side_effect = auth.PyJWKClientConnectionError("offline")
    monkeypatch.setattr(auth, "jwks_client", lambda _: provider)
    assert request(signing()).status_code == 503

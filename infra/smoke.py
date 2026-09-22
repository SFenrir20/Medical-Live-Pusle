"""HTTP smoke checks against the local Compose stack. No real data is modified."""

import json
import urllib.error
import urllib.request


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        return response.read().decode()


assert json.loads(get("http://127.0.0.1:8000/health")) == {"ok": True}
assert json.loads(get("http://127.0.0.1:8080/api/health")) == {"ok": True}
for route in ("/", "/home", "/forgot-password", "/history"):
    page = get("http://127.0.0.1:8080" + route)
    assert "<html" in page.lower() and "<script" in page.lower(), route

request = urllib.request.Request(
    "http://127.0.0.1:8080/api/v1/shifts/check-in",
    data=b'{"account_id":"medical"}',
    headers={"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(request, timeout=10)
    raise AssertionError("Una entrada sin autenticacion no debe aceptarse")
except urllib.error.HTTPError as exc:
    assert exc.code == 401, exc.code

print("OK: API, reverse proxy, SPA routes and unauthorized check-in")

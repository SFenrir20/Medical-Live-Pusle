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

# Medical Social Pulse: same /api prefix, routed to the right backend path.
SOCIAL = "http://127.0.0.1:8081"
assert "<html" in get(SOCIAL + "/").lower()
assert json.loads(get(SOCIAL + "/api/health")) == {"ok": True}
for base in (SOCIAL, "http://127.0.0.1:8080"):
    # Without a session these must answer 401 (route found, access denied), never 404.
    for route in ("/api/auth/me", "/api/inbox", "/api/marketing/tiktok/overview"):
        try:
            urllib.request.urlopen(base + route, timeout=10)
            raise AssertionError(route + " no debe aceptarse sin sesion")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401, (base, route, exc.code)

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

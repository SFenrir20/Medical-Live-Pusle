"""Read-only HTTP checks against the Social Pulse Compose stack."""
import json
import os
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:" + os.environ.get("WEB_PORT", "8080")


def get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.status == 200
        return response.read().decode()


assert json.loads(get("http://127.0.0.1:8000/health")) == {"ok": True}
assert json.loads(get(BASE + "/api/health")) == {"ok": True}
page = get(BASE + "/")
assert "<html" in page.lower() and "<script" in page.lower()
for route, expected in {
    "/api/auth/me": 401,
    "/api/inbox": 401,
    "/api/marketing/tiktok/overview": 401,
    "/api/v1/shifts/active": 404,
}.items():
    try:
        urllib.request.urlopen(BASE + route, timeout=10)
        raise AssertionError(route + " unexpectedly accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == expected, (route, exc.code)

print("OK: Social Pulse, API, reverse proxy, protected routes and retired attendance")

from types import SimpleNamespace

import pytest

from livepulse.modules.whatsapp import gateway


@pytest.mark.parametrize('path,minimum,maximum', [('/send', 46, 60), ('/status', 1, 20)])
async def test_transport_budget_allows_send_completion_but_keeps_probes_short(
    monkeypatch, path, minimum, maximum,
):
    observed = []
    monkeypatch.setattr(gateway, 'settings', SimpleNamespace(
        wa_gateway_url='http://internal-gateway', wa_gateway_token='x' * 32,
    ))

    class Client:
        def __init__(self, *, timeout):
            observed.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method, url, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'state': 'sent'})

    monkeypatch.setattr(gateway.httpx, 'AsyncClient', Client)
    assert await gateway.call(path, {} if path == '/send' else None) == {'state': 'sent'}
    assert minimum <= observed[0].read <= maximum
    assert observed[0].connect <= 5

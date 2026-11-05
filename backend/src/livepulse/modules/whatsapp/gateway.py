import httpx

from ...shared.config import settings


class GatewayUnavailable(Exception):
    pass


async def call(path: str, data=None):
    if not settings.wa_gateway_url or len(settings.wa_gateway_token) < 32:
        raise GatewayUnavailable('El espejo no está configurado en el servidor.')
    try:
        # The connector bounds a send at 45s. Keep HTTP above that bound; reads
        # and status probes retain the short budget so a slow send cannot hide them.
        timeout = httpx.Timeout(55 if path == '/send' else 20, connect=5)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request('GET' if data is None else 'POST',
                settings.wa_gateway_url.rstrip('/') + path, json=data,
                headers={'Authorization': f'Bearer {settings.wa_gateway_token}'})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GatewayUnavailable('No se pudo comunicar con el conector de WhatsApp.') from exc

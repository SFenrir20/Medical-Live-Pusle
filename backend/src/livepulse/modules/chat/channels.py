"""Channel adapters: the only place that knows how a message really leaves.

Flows, the AI agent and broadcasts call `send` through `adapter_for(channel)`. Moving from the
WhatsApp mirror to the official API means registering another adapter for the channel, not
touching any flow.

  simulator          records the message; used to build and test flows with no WhatsApp at all
  whatsapp_mirror    linked device (QR) through the `wa-gateway` service. NOT CONNECTED YET:
                     sending raises ChannelUnavailable until the gateway exists
  whatsapp_cloud     official API. NOT CONNECTED YET: waits for the approved credentials"""
from dataclasses import dataclass
from typing import Protocol


class ChannelUnavailable(RuntimeError):
    """The channel exists but cannot deliver right now (gateway down, API not configured)."""


@dataclass(frozen=True)
class Capabilities:
    free_text_anytime: bool      # False = only inside the provider's window (official API)
    templates: bool              # approved templates exist
    bulk_safe: bool              # provider tolerates mass sending (with good reputation)
    risky_automation: bool       # bots and mass sending can get the number restricted


CAPABILITIES = {
    'simulator': Capabilities(True, True, True, False),
    'whatsapp_mirror': Capabilities(True, False, False, True),
    'whatsapp_cloud': Capabilities(False, True, True, False),
}


@dataclass
class SendResult:
    external_id: str | None = None


class ChannelAdapter(Protocol):
    async def send(self, phone: str, text: str) -> SendResult: ...


class SimulatorAdapter:
    """Delivers nothing anywhere: the message is only stored by the chat core."""

    async def send(self, phone: str, text: str) -> SendResult:
        return SendResult(external_id=None)


class MirrorAdapter:
    async def send(self, phone: str, text: str) -> SendResult:
        raise ChannelUnavailable('El espejo de WhatsApp todavía no está vinculado.')


class CloudApiAdapter:
    async def send(self, phone: str, text: str) -> SendResult:
        raise ChannelUnavailable('La API oficial de WhatsApp todavía no está configurada.')


_ADAPTERS: dict[str, ChannelAdapter] = {
    'simulator': SimulatorAdapter(),
    'whatsapp_mirror': MirrorAdapter(),
    'whatsapp_cloud': CloudApiAdapter(),
}


def adapter_for(kind: str) -> ChannelAdapter:
    return _ADAPTERS[kind]


def register_adapter(kind: str, adapter: ChannelAdapter) -> None:
    """Plug in the real thing (gateway client, official API client) when it exists."""
    _ADAPTERS[kind] = adapter

"""What a channel allows, and the safe defaults.

The risk is real on the WhatsApp mirror (linked device, not the official API): bots and mass
messages are what most often gets a number restricted or blocked. So on that channel they are
OFF by default and, when an admin turns them on, they only reach the numbers of a test list and
inside strict caps. The official channel and the simulator are unrestricted by this policy
(the official API has its own 24-hour window rule).

An admin edits the overrides per channel (`ChatChannel.policy`); anything missing falls back to
the defaults of its kind."""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from .channels import CAPABILITIES
from .models import ChatChannel, ChatConversation, ChatMessage, OptOut

DEFAULTS: dict[str, dict] = {
    'simulator': {
        'bots_enabled': True, 'broadcasts_enabled': True, 'test_only': False, 'test_numbers': [],
        'bot_max_per_hour': 1000, 'broadcast_max_per_day': 10000, 'min_delay_s': 0,
        'window_hours': None},
    'whatsapp_mirror': {
        'bots_enabled': False, 'broadcasts_enabled': False, 'test_only': True, 'test_numbers': [],
        'bot_max_per_hour': 20, 'broadcast_max_per_day': 20, 'min_delay_s': 6,
        'window_hours': None},
    'whatsapp_cloud': {
        'bots_enabled': True, 'broadcasts_enabled': True, 'test_only': False, 'test_numbers': [],
        'bot_max_per_hour': 500, 'broadcast_max_per_day': 1000, 'min_delay_s': 1,
        'window_hours': 24},
}
EDITABLE = {'bots_enabled': bool, 'broadcasts_enabled': bool, 'test_only': bool,
            'test_numbers': list, 'bot_max_per_hour': int, 'broadcast_max_per_day': int,
            'min_delay_s': int}


class PolicyViolation(Exception):
    """An outbound message that the channel policy does not allow right now.
    `retry` means it may be fine later (rate limits): the worker tries again."""

    def __init__(self, code: str, message: str, retry: bool = False):
        super().__init__(message)
        self.code, self.message, self.retry = code, message, retry


def effective(channel: ChatChannel) -> dict:
    merged = dict(DEFAULTS[channel.kind])
    merged.update({k: v for k, v in (channel.policy or {}).items() if k in EDITABLE})
    return merged


def describe(channel: ChatChannel) -> dict:
    """What the admin screen shows, including why risky features need care."""
    capabilities = CAPABILITIES[channel.kind]
    return {'policy': effective(channel), 'defaults': DEFAULTS[channel.kind],
            'risky_automation': capabilities.risky_automation,
            'bulk_safe': capabilities.bulk_safe}


def clean_overrides(values: dict) -> dict:
    """Validate what an admin sends; unknown keys are rejected, numbers are bounded."""
    out = {}
    for key, value in values.items():
        if key not in EDITABLE:
            raise ValueError(f'Ajuste desconocido: {key}')
        if EDITABLE[key] is bool:
            out[key] = bool(value)
        elif EDITABLE[key] is list:
            out[key] = sorted({str(v).strip() for v in value if str(v).strip()})[:50]
        else:
            number = int(value)
            if not 0 <= number <= 100000:
                raise ValueError(f'{key} fuera de rango')
            out[key] = number
    return out


async def is_opted_out(session, phone: str) -> bool:
    return await session.get(OptOut, phone) is not None


async def _count(session, since: datetime, author_kind: str, *, broadcast: bool = False,
                 channel_id: str | None = None) -> int:
    query = select(func.count()).select_from(ChatMessage).join(
        ChatConversation, ChatConversation.id == ChatMessage.conversation_id).where(
        ChatMessage.direction == 'out', ChatMessage.author_kind == author_kind,
        ChatMessage.status == 'sent', ChatMessage.created_at >= since)
    if broadcast:
        query = query.where(ChatMessage.broadcast_id.is_not(None))
    if channel_id:
        query = query.where(ChatConversation.channel_id == channel_id)
    return await session.scalar(query) or 0


async def check_outbound(session, channel: ChatChannel, conversation: ChatConversation,
                         author_kind: str, now: datetime, *, broadcast: bool = False) -> None:
    """Raise PolicyViolation if this message may not be sent. People (agents) are only held
    to the channel being active and to the provider's reply window."""
    policy = effective(channel)
    if channel.status != 'active':
        raise PolicyViolation('channel_disabled', 'El canal está deshabilitado.')

    window = policy['window_hours']
    if window and author_kind in ('agent', 'bot') and not broadcast:
        last = conversation.last_inbound_at
        if last is None or now - last > timedelta(hours=window):
            raise PolicyViolation('window_closed',
                                  f'Pasaron más de {window} h desde su último mensaje: '
                                  'solo se puede enviar una plantilla aprobada.')

    automated = broadcast or author_kind == 'bot'
    if not automated:
        return
    if await is_opted_out(session, conversation.phone):
        raise PolicyViolation('opted_out', 'La persona pidió no recibir mensajes automáticos.')
    enabled = policy['broadcasts_enabled'] if broadcast else policy['bots_enabled']
    if not enabled:
        raise PolicyViolation(
            'broadcasts_disabled' if broadcast else 'bots_disabled',
            ('Las difusiones están apagadas' if broadcast else 'Los bots están apagados') +
            ' en este canal. Un administrador puede encenderlos.')
    if policy['test_only'] and conversation.phone not in policy['test_numbers']:
        raise PolicyViolation('test_only', 'Este canal solo envía automáticos a la lista de '
                                           'números de prueba.')
    if broadcast:
        sent_today = await _count(session, now - timedelta(days=1), 'bot', broadcast=True,
                                  channel_id=channel.id)
        if sent_today >= policy['broadcast_max_per_day']:
            raise PolicyViolation('daily_cap', 'Se alcanzó el tope diario de difusiones.')
    else:
        sent_hour = await _count(session, now - timedelta(hours=1), 'bot', channel_id=channel.id)
        if sent_hour >= policy['bot_max_per_hour']:
            raise PolicyViolation('bot_rate', 'Se alcanzó el tope de respuestas del bot por '
                                              'hora.', retry=True)
    if policy['min_delay_s']:
        recent = await session.scalar(select(func.max(ChatMessage.created_at)).join(
            ChatConversation, ChatConversation.id == ChatMessage.conversation_id).where(
            ChatConversation.channel_id == channel.id, ChatMessage.direction == 'out',
            ChatMessage.author_kind == 'bot', ChatMessage.status == 'sent'))
        if recent is not None:
            from ..social_live.service import aware_utc
            if (now - aware_utc(recent)).total_seconds() < policy['min_delay_s']:
                raise PolicyViolation('too_fast', 'Pausa mínima entre mensajes automáticos.',
                                      retry=True)

"""Where other modules listen to the chat core without the core knowing them."""
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)
Handler = Callable[..., Awaitable[None]]
_INBOUND: list[Handler] = []


def register_inbound(handler: Handler) -> None:
    if handler not in _INBOUND:
        _INBOUND.append(handler)


async def run_inbound(session, conversation, message) -> None:
    """A failing handler must never lose the incoming message: it is logged and skipped."""
    for handler in list(_INBOUND):
        try:
            async with session.begin_nested():
                await handler(session, conversation, message)
        except Exception:
            log.exception('Inbound handler %s failed', getattr(handler, '__name__', handler))

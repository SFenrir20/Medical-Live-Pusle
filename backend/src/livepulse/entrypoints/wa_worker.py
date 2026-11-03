"""One worker instance per mirror. No automation or broadcast execution here."""
import asyncio
import logging

from ..modules.whatsapp.service import tick
from ..shared.db import SessionLocal

logger = logging.getLogger(__name__)


async def main():
    while True:
        try:
            await tick(SessionLocal)
        except Exception as exc:
            # Do not log transport payloads, message bodies or credentials.
            logger.warning('WhatsApp sync will retry (%s)', type(exc).__name__)
        await asyncio.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

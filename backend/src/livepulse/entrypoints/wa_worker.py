"""One worker instance per mirror. No automation or broadcast execution here."""
import asyncio
import logging
import time
import traceback
from pathlib import Path

from ..modules.crm.scheduled import tick as send_scheduled
from ..modules.whatsapp.service import adopt_old_media, tick
from ..shared.db import SessionLocal

logger = logging.getLogger(__name__)


async def main():
    last_media_check = 0.0
    while True:
        try:
            await tick(SessionLocal)
        except Exception as exc:
            # Do not log transport payloads, message bodies or credentials.
            frames = traceback.extract_tb(exc.__traceback__)
            frame = frames[-1] if frames else None
            location = f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' if frame else 'unknown'
            logger.warning('WhatsApp sync will retry (error=%s location=%s)', type(exc).__name__, location)
        try:
            await send_scheduled(SessionLocal)  # messages agents scheduled; same outbox
        except Exception as exc:
            logger.warning('Scheduled messages will retry (error=%s)', type(exc).__name__)
        if time.monotonic() - last_media_check >= 60:
            last_media_check = time.monotonic()
            try:
                await adopt_old_media(SessionLocal)  # attach files to messages saved as text
            except Exception as exc:
                logger.warning('Old media recovery will retry (error=%s)', type(exc).__name__)
        await asyncio.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

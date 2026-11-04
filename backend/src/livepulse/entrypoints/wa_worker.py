"""One worker instance per mirror. No automation or broadcast execution here."""
import asyncio
import logging
import traceback
from pathlib import Path

from ..modules.whatsapp.service import tick
from ..shared.db import SessionLocal

logger = logging.getLogger(__name__)


async def main():
    while True:
        try:
            await tick(SessionLocal)
        except Exception as exc:
            # Do not log transport payloads, message bodies or credentials.
            frames = traceback.extract_tb(exc.__traceback__)
            frame = frames[-1] if frames else None
            location = f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' if frame else 'unknown'
            logger.warning('WhatsApp sync will retry (error=%s location=%s)', type(exc).__name__, location)
        await asyncio.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

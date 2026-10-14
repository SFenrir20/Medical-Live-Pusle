"""One-off repair: recover phone numbers in comments that were processed before the detector improved.

Comments such as "985//857#968" were stored with an empty phone list. This recomputes the phones of
every stored comment with the current detector and only ever ADDS what is missing.

  python -m livepulse.entrypoints.reprocess_phones            # dry run: counts only, writes nothing
  python -m livepulse.entrypoints.reprocess_phones --apply    # writes, in batches

Safe to repeat (a second run finds nothing) and to run while the worker is up. Output contains counts
only: never comment texts, usernames or phone numbers.
"""
import argparse
import asyncio
import logging
from uuid import uuid4

from ..modules.analytics.classify import phones_in

log = logging.getLogger(__name__)
ACTOR = 'system:reprocess-phones'


def missing_phones(stored, text) -> list[str]:
    """Phones the current detector finds in the text that the stored fact does not have yet."""
    return sorted(set(phones_in(text or '')) - set(stored or []))


async def reprocess(factory, apply=False, batch=200) -> dict:
    # Imported here so the decision logic above can be tested without a database driver.
    from sqlalchemy import select

    from ..modules.analytics.models import EventFact, LeadAudit
    from ..modules.analytics.processor import contact_for
    from ..modules.broadcasts.models import RawEvent

    stats = {'scanned': 0, 'comments_with_new_phones': 0, 'phones_added': 0, 'attached_to_contact': 0}
    last = ''
    while True:
        async with factory() as session, session.begin():
            rows = (await session.execute(
                select(EventFact.event_id, EventFact.phones, RawEvent.raw_text, RawEvent.payload)
                .join(RawEvent, RawEvent.event_id == EventFact.event_id)
                .where(EventFact.kind == 'comment', EventFact.event_id > last)
                .order_by(EventFact.event_id).limit(batch))).all()
            if not rows:
                break
            for row in rows:
                last = row.event_id
                stats['scanned'] += 1
                added = missing_phones(row.phones, row.raw_text)
                if not added:
                    continue
                stats['comments_with_new_phones'] += 1
                stats['phones_added'] += len(added)
                if not apply:
                    continue
                fact = await session.get(EventFact, row.event_id, with_for_update=True)
                phones = sorted(set(fact.phones or []) | set(added))
                # Same resolution as live processing: reuse the person known by user or number.
                lead_id = await contact_for(session, fact.user_key, (row.payload or {}).get('username'), phones)
                stats['attached_to_contact'] += fact.lead_id is None
                fact.phones = phones          # new list object, so the JSON change is detected
                fact.lead_id = lead_id
                session.add(LeadAudit(id=str(uuid4()), lead_id=lead_id, actor=ACTOR, action='phones',
                                      note=f'{len(added)} teléfono(s) recuperado(s) de un comentario anterior'))
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--apply', action='store_true', help='write the changes (default is a dry run)')
    parser.add_argument('--batch', type=int, default=200, help='comments per transaction')
    args = parser.parse_args(argv)
    from ..shared.db import SessionLocal

    stats = asyncio.run(reprocess(SessionLocal, apply=args.apply, batch=max(1, args.batch)))
    mode = 'APLICADO' if args.apply else 'SIMULACIÓN (no se escribió nada)'
    print(f'Recuperación de teléfonos · {mode}')
    print(f"  comentarios revisados:           {stats['scanned']}")
    print(f"  comentarios con teléfonos nuevos: {stats['comments_with_new_phones']}")
    print(f"  teléfonos recuperados:           {stats['phones_added']}")
    if args.apply:
        print(f"  comentarios que ahora tienen contacto: {stats['attached_to_contact']}")
    else:
        print('  Repite con --apply para guardarlos.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

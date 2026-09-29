"""Monitor TikTok adaptado del script manual a servicio multi-cuenta.

Base: script `scraper_tiktok.py` (TikTokLive 7.0.0, solo comentarios -> CSV).
Cambios para LivePulse:
- Un monitor por account_id (medical, medical-2) con reconexion propia.
- Comentarios + regalos + likes + shares + joins (metricas e interes).
- Cada evento lleva account_id + event_id global unico -> reprocesar es no-op.
- Desconexion != fin confirmado: solo LiveEnd + gracia/re-chequeo cierra el LIVE.
- Destino Postgres via sink (tests usan memoria, sin red).
"""
import argparse
import asyncio
import csv
import hashlib
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone

if sys.platform == "win32":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ..modules.broadcasts.sink import EventSink, MemorySink  # noqa: E402
from ..shared.config import settings  # noqa: E402


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_event_id(
    account_id: str, room_id: str | None, kind: str, provider_id: str | None, fallback: str
) -> str:
    """ID estable: el mismo evento redeliverado genera el mismo ID."""
    if provider_id:
        return f"{account_id}:{room_id or 'noroom'}:{kind}:{provider_id}"
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]
    return f"{account_id}:{room_id or 'noroom'}:{kind}:h{digest}"


def provider_msg_id(event) -> str | None:
    for attr in ("msg_id", "message_id", "id", "event_id"):
        value = getattr(event, attr, None)
        if value:
            return str(value)
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        for key in ("msg_id", "message_id", "id"):
            if data.get(key):
                return str(data[key])
    return None


def event_user(event) -> tuple[str, str | None]:
    user = getattr(event, "user", None)
    unique = getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "desconocido"
    nick = getattr(user, "nickname", None)
    return str(unique), (str(nick) if nick else None)


def normalize(kind: str, account_id: str, room_id: str | None, event, text: str | None,
              extra: dict | None = None) -> dict:
    unique, nick = event_user(event)
    occurred = utcnow()
    fallback = f"{account_id}|{kind}|{unique}|{text or ''}|{occurred.isoformat(timespec='seconds')}"
    return {
        "event_id": build_event_id(account_id, room_id, kind, provider_msg_id(event), fallback),
        "account_id": account_id,
        "broadcast_id": None,
        "type": kind,
        "occurred_at": occurred,
        "payload": {"user": unique, "nickname": nick, **(extra or {})},
        "raw_text": text,
    }


class BroadcastTracker:
    """Estado por cuenta. Un corte de red jamas confirma el fin."""

    def __init__(self, grace_s: float):
        self.grace = timedelta(seconds=grace_s)
        self.status = "offline"  # offline | live | ending
        self.room_id: str | None = None
        self.end_pending_at: datetime | None = None

    def on_connect(self, room_id: str | None = None):
        self.status = "live"
        self.room_id = room_id
        self.end_pending_at = None

    def on_disconnect(self):
        # Corte transitorio: se sigue en live hasta LiveEnd confirmado.
        if self.status == "live":
            pass  # espera reconexion con backoff

    def on_live_end(self, now: datetime | None = None):
        self.status = "ending"
        self.end_pending_at = now or utcnow()

    def confirm_end(self, now: datetime | None = None, recheck_offline: bool = True) -> bool:
        """True solo si paso la gracia y el re-chequeo dice offline."""
        now = now or utcnow()
        if self.status != "ending" or self.end_pending_at is None:
            return False
        if now - self.end_pending_at < self.grace:
            return False
        if not recheck_offline:
            return False
        self.status = "offline"
        self.end_pending_at = None
        return True


class AccountMonitor:
    def __init__(self, account_id: str, tiktok_username: str, sink: EventSink,
                 csv_path: str | None = None, timeout_s: int = 0):
        self.account_id = account_id
        self.username = tiktok_username
        self.sink = sink
        self.csv_path = csv_path
        self.timeout_s = timeout_s
        self.tracker = BroadcastTracker(grace_s=settings.monitor_end_grace_s)
        self._stop = asyncio.Event()

    def _csv_append(self, event: dict):
        if not self.csv_path:
            return
        exists = os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["event_id", "account_id", "type", "usuario", "texto"])
            writer.writerow([event["event_id"], event["account_id"], event["type"],
                             event["payload"].get("user"), event.get("raw_text")])

    async def _emit(self, event: dict):
        await self.sink.emit(event)
        self._csv_append(event)

    def attach(self, client):
        from TikTokLive.events import (
            CommentEvent,
            ConnectEvent,
            DisconnectEvent,
            GiftEvent,
            JoinEvent,
            LikeEvent,
            LiveEndEvent,
            ShareEvent,
        )

        async def on_connect(e):
            self.tracker.on_connect(room_id=getattr(getattr(client, "room", None), "id", None)
                                    or getattr(e, "room_id", None))
            print(f"[+] {self.account_id} (@{self.username}): conectado", flush=True)

        async def on_comment(e):
            await self._emit(normalize("comment", self.account_id, self.tracker.room_id,
                                       e, getattr(e, "comment", None)))

        async def on_gift(e):
            gift = getattr(e, "gift", None)
            await self._emit(normalize("gift", self.account_id, self.tracker.room_id, e, None, {
                "gift_name": getattr(gift, "name", None),
                "diamond_count": getattr(e, "diamond_count", getattr(e, "repeat_end", None)),
                "repeat_end": getattr(e, "repeat_end", None),
            }))

        async def on_like(e):
            await self._emit(normalize("like", self.account_id, self.tracker.room_id, e, None,
                                       {"count": getattr(e, "count", 1)}))

        async def on_share(e):
            await self._emit(normalize("share", self.account_id, self.tracker.room_id, e, None))

        async def on_join(e):
            await self._emit(normalize("join", self.account_id, self.tracker.room_id, e, None))

        async def on_live_end(e):
            print(f"[!] {self.account_id}: LiveEnd recibido, espera de gracia...", flush=True)
            self.tracker.on_live_end()
            await self._emit(normalize("live_end", self.account_id, self.tracker.room_id, e, None))
            asyncio.get_running_loop().call_later(
                settings.monitor_end_grace_s + 1, lambda: asyncio.create_task(client.disconnect()))

        async def on_disconnect(e):
            print(f"[!] {self.account_id}: conexion cerrada (no es fin confirmado).", flush=True)
            self.tracker.on_disconnect()

        client.add_listener(ConnectEvent, on_connect)
        client.add_listener(CommentEvent, on_comment)
        client.add_listener(GiftEvent, on_gift)
        client.add_listener(LikeEvent, on_like)
        client.add_listener(ShareEvent, on_share)
        client.add_listener(JoinEvent, on_join)
        client.add_listener(LiveEndEvent, on_live_end)
        client.add_listener(DisconnectEvent, on_disconnect)

    async def run_forever(self):
        from TikTokLive import TikTokLiveClient
        from TikTokLive.client.errors import UserNotFoundError, UserOfflineError

        delay = settings.monitor_reconnect_base_s
        while not self._stop.is_set():
            client = TikTokLiveClient(unique_id=self.username)
            self.attach(client)
            if self.timeout_s:
                asyncio.get_running_loop().call_later(
                    self.timeout_s, lambda c=client: asyncio.create_task(c.disconnect()))
            try:
                await client.connect(process_connect_events=True, compress_ws_events=True,
                                     fetch_live_check=True)
                delay = settings.monitor_reconnect_base_s  # exito: resetea backoff
                if self.tracker.status == "ending" and self.tracker.confirm_end(
                        recheck_offline=True):
                    print(f"[+] {self.account_id}: fin de LIVE confirmado.", flush=True)
                    return
            except (UserNotFoundError, UserOfflineError) as exc:
                if self.tracker.status == "ending":
                    if self.tracker.confirm_end(recheck_offline=True):
                        print(f"[+] {self.account_id}: fin confirmado (offline).", flush=True)
                        return
                print(f"[-] {self.account_id}: offline ({exc}). Reintento en {delay:.0f}s.",
                      flush=True)
            except Exception as exc:
                print(f"[X] {self.account_id}: error {exc}. Reintento en {delay:.0f}s.", flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.monitor_reconnect_max_s)

    def stop(self):
        self._stop.set()


async def main(accounts: tuple[str, ...] | None = None, timeout_s: int = 0,
               csv_prefix: str | None = None):
    from ..modules.broadcasts.sink import PostgresSink
    from ..shared.db import SessionLocal

    mapping = settings.tiktok_accounts
    wanted = accounts or tuple(mapping.keys())
    sink: EventSink = PostgresSink(SessionLocal)
    monitors = [AccountMonitor(a, mapping[a], sink, timeout_s=timeout_s,
                               csv_path=f"{csv_prefix}_{a}.csv" if csv_prefix else None)
                for a in wanted if a in mapping]
    await asyncio.gather(*(m.run_forever() for m in monitors))


def manual_run():
    """Validacion manual estilo script original: una cuenta, CSV debug opcional."""
    parser = argparse.ArgumentParser(description="Monitor TikTok LivePulse (validacion manual).")
    parser.add_argument("-a", "--account", default="medical",
                        help="account_id interno (medical | medical-2).")
    parser.add_argument("-u", "--user", default=None, help="Override usuario TikTok (sin @).")
    parser.add_argument("-t", "--timeout", type=int, default=0)
    parser.add_argument("-o", "--output", default=None, help="CSV debug.")
    args = parser.parse_args()
    username = args.user or settings.tiktok_accounts.get(args.account, args.account)
    monitor = AccountMonitor(args.account, username, MemorySink(),
                             csv_path=args.output, timeout_s=args.timeout)
    print(f"[+] Manual: {args.account} -> @{username} (memoria"
          + (f", CSV {args.output}" if args.output else "") + ")", flush=True)
    asyncio.run(monitor.run_forever())
    print(f"[+] Eventos capturados: {len(monitor.sink.events)}", flush=True)  # type: ignore


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-a", "--account", "-u", "--user", "-t", "-h"):
        manual_run()
    else:
        asyncio.run(main())

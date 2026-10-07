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
import json
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
    common_id = getattr(getattr(event, "common", None), "msg_id", None)
    if common_id:
        return str(common_id)
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        for key in ("msg_id", "message_id", "id"):
            if data.get(key):
                return str(data[key])
    return None


def event_user(event) -> tuple[str, str | None]:
    user = getattr(event, "user", None)
    unique = getattr(user, "id", None) or getattr(user, "unique_id", None) or ""
    nick = getattr(user, "nickname", None)
    return str(unique), (str(nick) if nick else None)


def normalize(kind: str, account_id: str, room_id: str | None, event, text: str | None,
              extra: dict | None = None) -> dict:
    unique, nick = event_user(event)
    occurred = utcnow()
    created = getattr(getattr(event, "common", None), "create_time", None)
    if created:
        try:
            occurred = datetime.fromtimestamp(float(created) / (1000 if float(created) > 1e12 else 1), timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    try:
        raw = bytes(event).hex()
    except (TypeError, ValueError):
        raw = json.dumps({"kind": kind, "user": unique, "text": text,
                          "extra": extra, "created": created}, sort_keys=True)
    fallback = raw
    return {
        "event_id": build_event_id(account_id, room_id, kind, provider_msg_id(event), fallback),
        "account_id": account_id,
        "broadcast_id": None,
        "type": kind,
        "occurred_at": occurred,
        "payload": {"user": unique, "nickname": nick,
                    "username": getattr(getattr(event, "user", None), "unique_id", None),
                    "dedup_quality": "provider" if provider_msg_id(event) else "fingerprint",
                    "time_source": "provider" if created else "received", **(extra or {})},
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
                 csv_path: str | None = None, timeout_s: int = 0, store=None):
        self.store = store
        self.broadcast_id = None
        self.connected = asyncio.Event()
        self.end_timer = None
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
        if self.store:
            await asyncio.wait_for(self.connected.wait(), timeout=30)
        event["broadcast_id"] = self.broadcast_id
        if self.store and not self.broadcast_id:
            raise RuntimeError("Cannot persist event without a LIVE")
        if await self.sink.emit(event):
            self._csv_append(event)

    def attach(self, client):
        from TikTokLive.events import (
            CommentEvent,
            ConnectEvent,
            DisconnectEvent,
            FollowEvent,
            GiftEvent,
            JoinEvent,
            LikeEvent,
            LiveEndEvent,
            RoomUserSeqEvent,
            ShareEvent,
        )

        async def on_connect(e):
            self.tracker.on_connect(room_id=getattr(getattr(client, "room", None), "id", None)
                                    or getattr(e, "room_id", None))
            if self.store:
                self.broadcast_id = await self.store.connected(
                    self.account_id, self.tracker.room_id, utcnow())
            self.connected.set()
            print(f"[+] {self.account_id} (@{self.username}): conectado", flush=True)

        async def emit(kind, event, text=None, extra=None):
            if self.store:
                await asyncio.wait_for(self.connected.wait(), timeout=30)
            await self._emit(normalize(kind, self.account_id, self.tracker.room_id,
                                       event, text, extra))

        async def on_comment(e):
            await emit("comment", e, getattr(e, "comment", None))

        async def on_gift(e):
            gift = getattr(e, "gift", None)
            await emit("gift", e, extra={
                "gift_name": getattr(gift, "name", None),
                "diamond_count": getattr(gift, "diamond_count", 0),
                "repeat_count": getattr(e, "repeat_count", 1),
                "gift_type": getattr(gift, "type", 0),
                "repeat_end": getattr(e, "repeat_end", None),
            })

        async def on_like(e):
            await emit("like", e, extra={"count": getattr(e, "count", 1)})

        async def on_share(e):
            await emit("share", e)

        async def on_join(e):
            await emit("join", e)

        async def on_follow(e):
            await emit("follow", e)

        async def on_audience(e):
            await emit("audience", e, extra={"viewers": getattr(e, "total", None)})

        async def on_live_end(e):
            self.tracker.on_live_end()
            await emit("live_end", e)
            self.end_timer = asyncio.get_running_loop().call_later(
                settings.monitor_end_grace_s + 1, lambda: asyncio.create_task(client.disconnect()))

        async def on_disconnect(e):
            print(f"[!] {self.account_id}: conexion cerrada (no es fin confirmado).", flush=True)
            self.tracker.on_disconnect()

        client.add_listener(ConnectEvent, on_connect)
        client.add_listener(CommentEvent, on_comment)
        client.add_listener(GiftEvent, on_gift)
        client.add_listener(LikeEvent, on_like)
        client.add_listener(ShareEvent, on_share)
        client.add_listener(FollowEvent, on_follow)
        client.add_listener(RoomUserSeqEvent, on_audience)
        client.add_listener(JoinEvent, on_join)
        client.add_listener(LiveEndEvent, on_live_end)
        client.add_listener(DisconnectEvent, on_disconnect)

    async def run_forever(self):
        from TikTokLive import TikTokLiveClient
        from TikTokLive.client.errors import UserNotFoundError, UserOfflineError

        delay = settings.monitor_reconnect_base_s
        while not self._stop.is_set():
            client = TikTokLiveClient(unique_id=self.username)
            self.connected.clear()
            self.attach(client)
            timeout = None
            heartbeat = None
            if self.timeout_s:
                timeout = asyncio.get_running_loop().call_later(
                    self.timeout_s, lambda c=client: asyncio.create_task(c.disconnect()))
            try:
                if self.store:
                    async def beat():
                        while True:
                            await self.store.touch(self.account_id, utcnow())
                            await asyncio.sleep(20)
                    # Heartbeat reports process activity, never a fabricated LIVE end.
                    heartbeat = asyncio.create_task(beat())
                await client.connect(process_connect_events=True, compress_ws_events=True,
                                     fetch_live_check=True)
                delay = settings.monitor_reconnect_base_s
                # An actual provider lookup is required after disconnection.
                live = await client.is_live()
                if self.store:
                    await self.store.observed(self.account_id, "reconnecting" if live else "offline",
                                              utcnow())
                if self.timeout_s:
                    return
            except UserOfflineError:
                if self.store:
                    await self.store.observed(self.account_id, "offline", utcnow())
            except UserNotFoundError:
                if self.store:
                    await self.store.observed(self.account_id, "error", utcnow(), "UserNotFound")
            except Exception as exc:
                if self.store:
                    await self.store.observed(self.account_id, "error", utcnow(), type(exc).__name__)
                print(f"[X] {self.account_id}: {type(exc).__name__}; retry in {delay}s", flush=True)
            finally:
                if timeout:
                    timeout.cancel()
                if self.end_timer:
                    self.end_timer.cancel()
                    self.end_timer = None
                if heartbeat:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                await client.close()
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.monitor_reconnect_max_s)

    def stop(self):
        self._stop.set()


async def main(accounts: tuple[str, ...] | None = None, timeout_s: int = 0,
               csv_prefix: str | None = None):
    from ..modules.broadcasts.lifecycle import BroadcastStore
    from ..modules.broadcasts.sink import PostgresSink
    from ..shared.db import SessionLocal

    mapping = settings.tiktok_accounts
    wanted = accounts or tuple(mapping.keys())
    sink: EventSink = PostgresSink(SessionLocal)
    store = BroadcastStore(SessionLocal)
    monitors = [AccountMonitor(a, mapping[a], sink, timeout_s=timeout_s, store=store,
                               csv_path=f"{csv_prefix}_{a}.csv" if csv_prefix else None)
                for a in wanted if a in mapping]
    async def run_owned(monitor):
        while True:
            async with store.lease(monitor.account_id) as owned:
                if owned:
                    await monitor.run_forever()
            await asyncio.sleep(30)
    await asyncio.gather(*(run_owned(m) for m in monitors))


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

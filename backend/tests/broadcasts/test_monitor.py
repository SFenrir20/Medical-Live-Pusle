import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from livepulse.entrypoints.monitor import (  # noqa: E402
    BroadcastTracker,
    MemorySink,
    build_event_id,
    normalize,
)


def fake_event(msg_id="m1", user="ana", nick="Ana", comment="hola"):
    return SimpleNamespace(msg_id=msg_id, comment=comment,
                           user=SimpleNamespace(unique_id=user, nickname=nick))


def test_event_id_estable_ante_redelivery():
    same = build_event_id("medical", "r1", "comment", "m1", "x")
    assert build_event_id("medical", "r1", "comment", "m1", "y") == same


def test_event_id_distinto_por_cuenta_y_tipo():
    a = build_event_id("medical", "r1", "comment", "m1", "x")
    assert build_event_id("medical-2", "r1", "comment", "m1", "x") != a
    assert build_event_id("medical", "r1", "gift", "m1", "x") != a


@pytest.mark.asyncio
async def test_sink_dedup_reprocesar_es_noop():
    sink = MemorySink()
    event = normalize("comment", "medical", "r1", fake_event(), "hola")
    assert await sink.emit(event) is True
    assert await sink.emit(event) is False  # redelivery
    assert len(sink.events) == 1


@pytest.mark.asyncio
async def test_eventos_fuera_de_orden_se_aceptan():
    sink = MemorySink()
    for mid in ("m3", "m1", "m2"):  # llegan desordenados
        await sink.emit(normalize("comment", "medical", "r1", fake_event(msg_id=mid), mid))
    assert len(sink.events) == 3


def test_desconexion_no_confirma_fin():
    tracker = BroadcastTracker(grace_s=60)
    tracker.on_connect(room_id="r1")
    tracker.on_disconnect()  # corte de red
    assert tracker.confirm_end(recheck_offline=True) is False
    assert tracker.status == "live"


def test_live_end_requiere_gracia_y_recheck():
    tracker = BroadcastTracker(grace_s=120)
    tracker.on_connect(room_id="r1")
    tracker.on_live_end()
    assert tracker.confirm_end(recheck_offline=True) is False  # gracia no pasada
    future = tracker.end_pending_at + timedelta(seconds=121)
    assert tracker.confirm_end(now=future, recheck_offline=False) is False  # sin recheck no
    assert tracker.confirm_end(now=future, recheck_offline=True) is True
    assert tracker.status == "offline"


@pytest.mark.asyncio
async def test_cuentas_no_se_mezclan():
    sink = MemorySink()
    for account in ("medical", "medical-2"):
        await sink.emit(normalize("comment", account, "rX", fake_event(), "hola"))
    assert len(sink.events) == 2

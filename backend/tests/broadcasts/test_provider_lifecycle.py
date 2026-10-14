"""Use the installed TikTokLive SDK offline to exercise shared-loop cleanup."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
import TikTokLive
from TikTokLive.client.errors import UserOfflineError

from livepulse.entrypoints.monitor import AccountMonitor, close_provider
from livepulse.modules.broadcasts.sink import MemorySink
from livepulse.shared.config import settings


async def test_sdk_cleanup_closes_http_without_cancelling_other_accounts():
    client = TikTokLive.TikTokLiveClient(unique_id='test')
    sibling = asyncio.create_task(asyncio.Event().wait())
    try:
        await close_provider(client)
        assert client.web._httpx.is_closed
        assert not sibling.done()
    finally:
        sibling.cancel()
        await asyncio.gather(sibling, return_exceptions=True)


async def test_offline_account_retries_and_closes_each_sdk_client(monkeypatch):
    monitor = AccountMonitor('medical', 'test', MemorySink())
    clients = [TikTokLive.TikTokLiveClient(unique_id='test') for _ in range(2)]
    clients[0].start = AsyncMock(side_effect=UserOfflineError())

    async def connected(**kwargs):
        monitor.stop()
        return asyncio.create_task(asyncio.sleep(0))

    clients[1].start = AsyncMock(side_effect=connected)
    clients[1].is_live = AsyncMock(return_value=True)
    for client in clients:
        client._clean_tasks = Mock(side_effect=AssertionError('Unsafe synchronous cleanup'))
        client.connect = AsyncMock(side_effect=AssertionError('Use start on the shared loop'))
    factory = Mock(side_effect=clients)
    monkeypatch.setattr(TikTokLive, 'TikTokLiveClient', factory)
    monkeypatch.setattr(settings, 'monitor_reconnect_base_s', 0)
    await monitor.run_forever()
    assert factory.call_count == 2
    for client in clients:
        assert client.web._httpx.is_closed
        client.start.assert_awaited_once()
        client._clean_tasks.assert_not_called()


async def test_shutdown_drains_stream_and_preserves_cancellation(monkeypatch):
    monitor = AccountMonitor('medical', 'test', MemorySink())
    client = TikTokLive.TikTokLiveClient(unique_id='test')
    running = asyncio.Event()
    released = asyncio.Event()
    stream = asyncio.create_task(released.wait())

    async def start(**kwargs):
        running.set()
        return stream

    async def disconnect():
        released.set()
        await stream

    client.start = AsyncMock(side_effect=start)
    client.disconnect = AsyncMock(side_effect=disconnect)
    client._clean_tasks = Mock(side_effect=AssertionError('Unsafe synchronous cleanup'))
    monkeypatch.setattr(TikTokLive, 'TikTokLiveClient', lambda **kwargs: client)
    task = asyncio.create_task(monitor.run_forever())
    await asyncio.wait_for(running.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.done() and not stream.cancelled()
    assert client.web._httpx.is_closed
    client.disconnect.assert_awaited_once()
    client._clean_tasks.assert_not_called()


async def test_disconnect_failure_still_releases_http_client():
    client = TikTokLive.TikTokLiveClient(unique_id='test')
    client.disconnect = AsyncMock(side_effect=RuntimeError('simulated disconnect failure'))
    with pytest.raises(RuntimeError, match='simulated disconnect failure'):
        await close_provider(client)
    assert client.web._httpx.is_closed

from __future__ import annotations

import asyncio

import pytest

from quote_service.models import Quote
from quote_service.store import QuoteStore


def _quote(
    symbol: str = "BTCUSDT",
    bid: float = 50000.0,
    ask: float = 50001.0,
    event_time: int = 1700000000000,
) -> Quote:
    return Quote(
        symbol=symbol,
        bid_price=bid,
        bid_size=1.0,
        ask_price=ask,
        ask_size=1.0,
        event_time=event_time,
        receive_time_ns=0,
    )


class TestInMemoryStore:
    @pytest.mark.asyncio
    async def test_get_latest_empty(self, store: QuoteStore):
        assert store.get_latest("BTCUSDT") is None

    @pytest.mark.asyncio
    async def test_update_and_get(self, store: QuoteStore):
        q = _quote()
        store.update(q)
        result = store.get_latest("BTCUSDT")
        assert result is not None
        assert result.bid_price == 50000.0

    @pytest.mark.asyncio
    async def test_update_overwrites(self, store: QuoteStore):
        store.update(_quote(bid=50000.0))
        store.update(_quote(bid=51000.0))
        result = store.get_latest("BTCUSDT")
        assert result is not None
        assert result.bid_price == 51000.0

    @pytest.mark.asyncio
    async def test_get_all_latest(self, store: QuoteStore):
        store.update(_quote(symbol="BTCUSDT"))
        store.update(_quote(symbol="ETHUSDT", bid=3000.0, ask=3001.0))
        all_q = store.get_all_latest()
        assert len(all_q) == 2
        assert "BTCUSDT" in all_q
        assert "ETHUSDT" in all_q

    @pytest.mark.asyncio
    async def test_case_insensitive_lookup(self, store: QuoteStore):
        store.update(_quote(symbol="BTCUSDT"))
        assert store.get_latest("btcusdt") is not None
        assert store.get_latest("BtCuSdT") is not None


class TestSQLitePersistence:
    @pytest.mark.asyncio
    async def test_flush_writes_to_db(self, store: QuoteStore):
        store.update(_quote())
        n = await store.flush()
        assert n == 1

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self, store: QuoteStore):
        n = await store.flush()
        assert n == 0

    @pytest.mark.asyncio
    async def test_batch_flush(self, store: QuoteStore):
        for i in range(25):
            store.update(_quote(event_time=1700000000000 + i))
        n = await store.flush()
        assert n == 25

    @pytest.mark.asyncio
    async def test_history_query(self, store: QuoteStore):
        for i in range(5):
            store.update(_quote(event_time=1700000000000 + i))
        await store.flush()
        history = await store.get_history("BTCUSDT", limit=3)
        assert len(history) == 3
        # Should be ordered DESC by event_time
        assert history[0]["event_time_ms"] > history[2]["event_time_ms"]

    @pytest.mark.asyncio
    async def test_history_empty(self, store: QuoteStore):
        history = await store.get_history("NONEXIST")
        assert history == []

    @pytest.mark.asyncio
    async def test_close_flushes_remaining(self, tmp_path):
        db_path = str(tmp_path / "close_test.db")
        s = QuoteStore(db_path=db_path, batch_size=10)
        await s.init_db()
        s.update(_quote())
        await s.close()

        # Reopen and verify data was flushed
        s2 = QuoteStore(db_path=db_path, batch_size=10)
        await s2.init_db()
        history = await s2.get_history("BTCUSDT")
        assert len(history) == 1
        await s2.close()

    @pytest.mark.asyncio
    async def test_concurrent_read_during_flush(self, store: QuoteStore):
        """In-memory reads should not block during flush."""
        for i in range(100):
            store.update(_quote(event_time=1700000000000 + i))

        async def read_loop():
            for _ in range(50):
                store.get_latest("BTCUSDT")
                await asyncio.sleep(0)

        # Both should complete without deadlock
        await asyncio.gather(store.flush(), read_loop())

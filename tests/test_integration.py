from __future__ import annotations

import asyncio
import json

import pytest
import websockets
import websockets.asyncio.server
from httpx import ASGITransport, AsyncClient

from quote_service.api import create_app
from quote_service.config import Settings
from quote_service.main import flush_loop
from quote_service.store import QuoteStore
from quote_service.ws_client import BinanceWSClient


def _book_ticker_msg(symbol: str, bid: str, ask: str) -> str:
    return json.dumps(
        {
            "stream": f"{symbol.lower()}@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 123456,
                "E": 1700000000000,
                "T": 1699999999999,
                "s": symbol,
                "b": bid,
                "B": "1.0",
                "a": ask,
                "A": "2.0",
            },
        }
    )


class TestFlushLoop:
    @pytest.mark.asyncio
    async def test_continues_after_flush_error(self, tmp_path):
        """flush_loop must survive a failing flush() and keep running."""
        store = QuoteStore(db_path=str(tmp_path / "err.db"))
        await store.init_db()

        call_count = 0
        original_flush = store.flush

        async def flaky_flush() -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("disk full")
            return await original_flush()

        store.flush = flaky_flush  # type: ignore[assignment]

        stop_event = asyncio.Event()
        task = asyncio.create_task(flush_loop(store, 0.05, stop_event))

        # Wait long enough for at least 3 flush cycles
        await asyncio.sleep(0.25)
        stop_event.set()
        await task

        # The loop must have called flush multiple times despite the first error
        assert call_count >= 3
        await store.close()


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, tmp_path):
        """Mock WS -> WS Client -> Store -> API."""
        symbols = ["BTCUSDT", "ETHUSDT"]

        async def handler(ws):
            for sym, bid, ask in [
                ("BTCUSDT", "50000.00", "50001.00"),
                ("ETHUSDT", "3000.00", "3001.00"),
                ("BTCUSDT", "50100.00", "50101.00"),  # update
            ]:
                await ws.send(_book_ticker_msg(sym, bid, ask))
            await asyncio.sleep(2.0)  # keep connection alive

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=symbols,
                spot_ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "integ.db"),
                batch_interval_ms=50,
            )

            store = QuoteStore(db_path=settings.db_path)
            await store.init_db()

            ws_client = BinanceWSClient(settings.symbols, settings.spot_ws_url, store)
            app = create_app(store)

            stop_event = asyncio.Event()
            ws_task = asyncio.create_task(ws_client.run())
            flush_task = asyncio.create_task(
                flush_loop(store, settings.batch_interval_ms / 1000.0, stop_event)
            )

            try:
                # Wait for all quotes to be processed
                for _ in range(30):
                    await asyncio.sleep(0.1)
                    if len(store.get_all_latest()) == 2:
                        btc = store.get_latest("BTCUSDT")
                        if btc and btc.bid_price == 50100.0:
                            break

                # Verify in-memory state
                latest = store.get_all_latest()
                assert len(latest) == 2
                assert latest["BTCUSDT"].bid_price == 50100.0  # latest update
                assert latest["ETHUSDT"].bid_price == 3000.0

                # Verify via API
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/quotes")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert len(data) == 2

                    resp = await client.get("/quotes/BTCUSDT")
                    assert resp.status_code == 200
                    assert resp.json()["bid_price"] == 50100.0

                    resp = await client.get("/quotes/ETHUSDT")
                    assert resp.status_code == 200
                    assert resp.json()["bid_price"] == 3000.0

                    resp = await client.get("/health")
                    assert resp.json()["symbols_active"] == 2

                # Wait for flush and verify DB persistence
                await asyncio.sleep(0.2)
                await store.flush()
                history = await store.get_history("BTCUSDT")
                assert len(history) >= 2  # At least the two BTCUSDT quotes
            finally:
                ws_client.stop()
                stop_event.set()
                ws_task.cancel()
                try:
                    await ws_task
                except asyncio.CancelledError:
                    pass
                await flush_task
                await store.close()

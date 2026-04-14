from __future__ import annotations

import asyncio
import json

import pytest
import websockets
import websockets.asyncio.server

from quote_service.config import Settings
from quote_service.store import QuoteStore
from quote_service.ws_client import BinanceWSClient


def _book_ticker_msg(symbol: str = "BTCUSDT", bid: str = "50000.00", ask: str = "50001.00") -> str:
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


async def _wait_for_store(store: QuoteStore, symbol: str, *, expected_bid: float | None = None, timeout: float = 5.0):
    """Poll the store until the expected quote appears."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        q = store.get_latest(symbol)
        if q is not None:
            if expected_bid is None or q.bid_price == expected_bid:
                return q
        await asyncio.sleep(0.01)
    raise TimeoutError(f"Quote for {symbol} (bid={expected_bid}) not found in store within {timeout}s")


class TestWSClient:
    @pytest.mark.asyncio
    async def test_receives_quotes(self, tmp_path):
        """WS client should parse bookTicker messages and update the store."""
        send_count = 5

        async def handler(ws):
            for i in range(send_count):
                await ws.send(_book_ticker_msg(bid=str(50000 + i)))
            await asyncio.sleep(0.5)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                spot_ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            store = QuoteStore(db_path=settings.db_path)
            await store.init_db()
            client = BinanceWSClient(settings.symbols, settings.spot_ws_url, store)

            task = asyncio.create_task(client.run())
            try:
                # Last message has bid=50004, wait for that
                q = await _wait_for_store(store, "BTCUSDT", expected_bid=50004.0)
                assert q.symbol == "BTCUSDT"
                assert q.bid_price == 50004.0
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await store.close()

    @pytest.mark.asyncio
    async def test_skips_malformed_messages(self, tmp_path):
        """WS client should skip messages with missing fields."""

        async def handler(ws):
            # Send a malformed message (missing 'b' field)
            await ws.send(json.dumps({
                "stream": "btcusdt@bookTicker",
                "data": {"s": "BTCUSDT", "E": 1700000000000},
            }))
            # Followed by a valid one
            await ws.send(_book_ticker_msg())
            await asyncio.sleep(0.5)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                spot_ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            store = QuoteStore(db_path=settings.db_path)
            await store.init_db()
            client = BinanceWSClient(settings.symbols, settings.spot_ws_url, store)

            task = asyncio.create_task(client.run())
            try:
                q = await _wait_for_store(store, "BTCUSDT")
                assert q.symbol == "BTCUSDT"
                assert q.bid_price == 50000.0
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await store.close()

    @pytest.mark.asyncio
    async def test_reconnects_on_disconnect(self, tmp_path):
        """WS client should reconnect after server disconnects."""
        connection_count = 0

        async def handler(ws):
            nonlocal connection_count
            connection_count += 1
            if connection_count == 1:
                # First connection: send one message then close
                await ws.send(_book_ticker_msg())
                await ws.close()
            else:
                # Second connection: send another message
                await ws.send(_book_ticker_msg(bid="51000.00"))
                await asyncio.sleep(2.0)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                spot_ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            store = QuoteStore(db_path=settings.db_path)
            await store.init_db()
            client = BinanceWSClient(settings.symbols, settings.spot_ws_url, store)

            task = asyncio.create_task(client.run())
            try:
                # After reconnect, store should have the updated bid
                q = await _wait_for_store(store, "BTCUSDT", expected_bid=51000.0, timeout=10.0)
                assert q.bid_price == 51000.0
                assert connection_count == 2
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await store.close()

    @pytest.mark.asyncio
    async def test_url_construction(self, tmp_path):
        """Verify the combined stream URL is built correctly."""
        store = QuoteStore(db_path=str(tmp_path / "test.db"))
        client = BinanceWSClient(["BTCUSDT", "ETHUSDT"], "wss://fstream.binance.com", store)
        assert "btcusdt@bookTicker" in client._url
        assert "ethusdt@bookTicker" in client._url
        assert "/stream?streams=" in client._url

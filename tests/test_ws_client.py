from __future__ import annotations

import asyncio
import json

import pytest
import websockets
import websockets.asyncio.server

from quote_service.config import Settings
from quote_service.models import Quote
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


class TestWSClient:
    @pytest.mark.asyncio
    async def test_receives_quotes(self, tmp_path):
        """WS client should parse bookTicker messages and put them on the queue."""
        received: list[Quote] = []
        send_count = 5

        async def handler(ws):
            for i in range(send_count):
                await ws.send(_book_ticker_msg(bid=str(50000 + i)))
            # Keep connection open briefly so client processes messages
            await asyncio.sleep(0.2)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            queue: asyncio.Queue[Quote] = asyncio.Queue()
            client = BinanceWSClient(settings, queue)

            task = asyncio.create_task(client.run())
            try:
                for _ in range(send_count):
                    q = await asyncio.wait_for(queue.get(), timeout=5.0)
                    received.append(q)
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        assert len(received) == send_count
        assert received[0].symbol == "BTCUSDT"
        assert received[0].bid_price == 50000.0
        assert received[4].bid_price == 50004.0

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
            await asyncio.sleep(0.2)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            queue: asyncio.Queue[Quote] = asyncio.Queue()
            client = BinanceWSClient(settings, queue)

            task = asyncio.create_task(client.run())
            try:
                q = await asyncio.wait_for(queue.get(), timeout=5.0)
                assert q.symbol == "BTCUSDT"
                assert q.bid_price == 50000.0
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

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
                await asyncio.sleep(1.0)

        async with websockets.asyncio.server.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(
                symbols=["BTCUSDT"],
                ws_url=f"ws://127.0.0.1:{port}",
                db_path=str(tmp_path / "test.db"),
            )
            queue: asyncio.Queue[Quote] = asyncio.Queue()
            client = BinanceWSClient(settings, queue)

            task = asyncio.create_task(client.run())
            try:
                q1 = await asyncio.wait_for(queue.get(), timeout=5.0)
                assert q1.bid_price == 50000.0
                q2 = await asyncio.wait_for(queue.get(), timeout=10.0)
                assert q2.bid_price == 51000.0
                assert connection_count == 2
            finally:
                client.stop()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_url_construction(self, tmp_path):
        """Verify the combined stream URL is built correctly."""
        settings = Settings(
            symbols=["BTCUSDT", "ETHUSDT"],
            ws_url="wss://fstream.binance.com",
            db_path=str(tmp_path / "test.db"),
        )
        queue: asyncio.Queue[Quote] = asyncio.Queue()
        client = BinanceWSClient(settings, queue)
        assert "btcusdt@bookTicker" in client._url
        assert "ethusdt@bookTicker" in client._url
        assert "/stream?streams=" in client._url

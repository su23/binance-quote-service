from __future__ import annotations

import asyncio
import logging
import ssl

import certifi
import orjson
import websockets
import websockets.asyncio.client

from .models import parse_book_ticker
from .store import QuoteStore

logger = logging.getLogger(__name__)

MAX_RECONNECT_DELAY = 30.0
INITIAL_RECONNECT_DELAY = 1.0


class BinanceWSClient:
    """Connects to Binance combined bookTicker stream and updates the store directly."""

    def __init__(
        self,
        symbols: list[str],
        ws_url: str,
        store: QuoteStore,
        label: str = "",
    ) -> None:
        self._symbols = symbols
        self._store = store
        self._running = False
        self._label = label or ws_url
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._received = 0
        streams = "/".join(
            f"{s.lower()}@bookTicker" for s in symbols
        )
        self._url = f"{ws_url}/stream?streams={streams}"

    async def run(self) -> None:
        """Run the WebSocket listener with auto-reconnect."""
        self._running = True
        delay = INITIAL_RECONNECT_DELAY
        while self._running:
            self._received = 0
            try:
                await self._connect_and_listen()
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError,
            ) as exc:
                if not self._running:
                    break
                # If we received messages, the connection was healthy before
                # it dropped — reset delay instead of escalating.
                if self._received > 0:
                    delay = INITIAL_RECONNECT_DELAY
                logger.warning(
                    "[%s] WebSocket disconnected after %d msgs: %s. Reconnecting in %.1fs…",
                    self._label,
                    self._received,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _connect_and_listen(self) -> None:
        """Connect and stream messages until disconnected."""
        logger.info("[%s] Connecting to %s", self._label, self._url)
        ssl_ctx: ssl.SSLContext | None = None
        if self._url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        async with websockets.asyncio.client.connect(
            self._url,
            ssl=ssl_ctx,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            logger.info("[%s] Connected. Streaming bookTicker for %d symbols.", self._label, len(self._symbols))
            async for raw in ws:
                if not self._running:
                    break
                msg = orjson.loads(raw)
                data = msg.get("data")
                if data is None:
                    continue
                try:
                    quote = parse_book_ticker(data)
                except (KeyError, ValueError) as exc:
                    logger.debug("Skipping malformed message: %s", exc)
                    continue
                self._store.update(quote)
                self._received += 1
        self._ws = None

    def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            self._ws.close_timeout = 1
            asyncio.ensure_future(self._ws.close())

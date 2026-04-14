from __future__ import annotations

import asyncio
import json
import logging
import ssl

import certifi
import websockets
import websockets.asyncio.client

from .config import Settings
from .models import Quote, parse_book_ticker

logger = logging.getLogger(__name__)

MAX_RECONNECT_DELAY = 30.0


class BinanceWSClient:
    """Connects to Binance combined bookTicker stream and pushes Quotes to a queue."""

    def __init__(self, settings: Settings, queue: asyncio.Queue[Quote]) -> None:
        self._settings = settings
        self._queue = queue
        self._running = False
        streams = "/".join(
            f"{s.lower()}@bookTicker" for s in settings.symbols
        )
        self._url = f"{settings.ws_url}/stream?streams={streams}"

    async def run(self) -> None:
        """Run the WebSocket listener with auto-reconnect."""
        self._running = True
        delay = 1.0
        while self._running:
            try:
                received = await self._connect_and_listen()
                # If we received data, the connection was healthy — reset delay
                if received:
                    delay = 1.0
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError,
            ) as exc:
                if not self._running:
                    break
                logger.warning(
                    "WebSocket disconnected: %s. Reconnecting in %.1fs…",
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _connect_and_listen(self) -> int:
        """Connect and stream messages. Returns the number of messages received."""
        logger.info("Connecting to %s", self._url)
        ssl_ctx: ssl.SSLContext | None = None
        if self._url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        received = 0
        async with websockets.asyncio.client.connect(
            self._url,
            ssl=ssl_ctx,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=5,
        ) as ws:
            logger.info("Connected. Streaming bookTicker for %d symbols.", len(self._settings.symbols))
            async for raw in ws:
                if not self._running:
                    break
                msg = json.loads(raw)
                data = msg.get("data")
                if data is None:
                    continue
                try:
                    quote = parse_book_ticker(data)
                except (KeyError, ValueError) as exc:
                    logger.debug("Skipping malformed message: %s", exc)
                    continue
                try:
                    self._queue.put_nowait(quote)
                except asyncio.QueueFull:
                    pass  # drop quote under backpressure
                received += 1
        return received

    def stop(self) -> None:
        self._running = False

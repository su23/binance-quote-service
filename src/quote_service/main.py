from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from .api import create_app
from .config import FALLBACK_SYMBOLS, Settings
from .instruments import fetch_top_instruments
from .models import Quote
from .store import QuoteStore
from .ws_client import BinanceWSClient

logger = logging.getLogger(__name__)


async def process_quotes(
    queue: asyncio.Queue[Quote],
    store: QuoteStore,
    batch_interval_s: float,
) -> None:
    """Read quotes from the queue, update store, and periodically flush to DB."""

    async def _flusher() -> None:
        while True:
            await asyncio.sleep(batch_interval_s)
            n = await store.flush()
            if n:
                logger.debug("Flushed %d quotes to DB", n)

    flush_task = asyncio.create_task(_flusher())
    try:
        while True:
            quote = await queue.get()
            store.update(quote)
    finally:
        flush_task.cancel()
        await store.flush()


async def run(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Auto-discover top instruments if none specified
    if not settings.symbols:
        try:
            settings.symbols = await fetch_top_instruments(
                n=settings.num_instruments, base_url=settings.rest_url
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch top instruments (%s), using fallback list", exc
            )
            settings.symbols = FALLBACK_SYMBOLS[: settings.num_instruments]

    logger.info(
        "Starting Binance Quote Service for %d symbols: %s",
        len(settings.symbols),
        ", ".join(settings.symbols),
    )

    store = QuoteStore(db_path=settings.db_path, batch_size=settings.batch_size)
    await store.init_db()

    queue: asyncio.Queue[Quote] = asyncio.Queue(maxsize=10_000)
    ws_client = BinanceWSClient(settings, queue)

    app = create_app(store)
    uvi_config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        loop="none",
    )
    server = uvicorn.Server(uvi_config)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown() -> None:
        logger.info("Shutdown signal received")
        ws_client.stop()
        stop_event.set()
        server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    batch_interval_s = settings.batch_interval_ms / 1000.0

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(ws_client.run())
            tg.create_task(process_quotes(queue, store, batch_interval_s))
            tg.create_task(server.serve())
    except* KeyboardInterrupt:
        pass
    finally:
        await store.close()
        logger.info("Shutdown complete")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

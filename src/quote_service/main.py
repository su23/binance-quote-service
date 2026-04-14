from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from .api import create_app
from .config import FALLBACK_SYMBOLS, Settings
from .instruments import fetch_top_instruments
from .store import QuoteStore
from .ws_client import BinanceWSClient

logger = logging.getLogger(__name__)


async def flush_loop(store: QuoteStore, interval_s: float, stop_event: asyncio.Event) -> None:
    """Periodically flush buffered quotes to SQLite until stop_event is set."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass
        n = await store.flush()
        if n:
            logger.debug("Flushed %d quotes to DB", n)


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

    ws_client = BinanceWSClient(settings, store)

    app = create_app(store)
    uvi_config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        loop="none",
    )
    server = uvicorn.Server(uvi_config)
    # Prevent uvicorn from installing its own signal handlers (we handle it)
    server.install_signal_handlers = lambda: None

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown() -> None:
        if stop_event.is_set():
            return
        logger.info("Shutdown signal received")
        ws_client.stop()
        server.should_exit = True
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    batch_interval_s = settings.batch_interval_ms / 1000.0

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(ws_client.run())
            tg.create_task(flush_loop(store, batch_interval_s, stop_event))
            tg.create_task(server.serve())
    except* (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await store.close()
        logger.info("Shutdown complete")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

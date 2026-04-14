from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from .api import create_app
from .config import FALLBACK_SYMBOLS, Settings
from .instruments import fetch_futures_symbols, fetch_top_instruments
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
        try:
            n = await store.flush()
        except Exception:
            logger.exception("Failed to flush quotes to DB")
        else:
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
                n=settings.num_instruments,
            )
        except Exception as exc:
            logger.warning(
                "=== AUTO-DISCOVERY FAILED === "
                "Could not fetch top instruments from Binance (%s: %s). "
                "This may be caused by rate-limiting or network issues. "
                "Falling back to hardcoded symbol list. "
                "Set QS_SYMBOLS to override.",
                type(exc).__name__,
                exc,
            )
            settings.symbols = FALLBACK_SYMBOLS[: settings.num_instruments]

    # Split symbols: futures for those with perpetuals, spot for the rest.
    try:
        futures_available = await fetch_futures_symbols(
            base_url=settings.futures_rest_url + "/fapi/v1/exchangeInfo",
        )
    except Exception as exc:
        logger.warning("Failed to fetch futures symbols (%s), using spot for all", exc)
        futures_available = set()

    futures_symbols = [s for s in settings.symbols if s in futures_available]
    spot_symbols = [s for s in settings.symbols if s not in futures_available]

    logger.info(
        "Starting Binance Quote Service for %d symbols: %s",
        len(settings.symbols),
        ", ".join(settings.symbols),
    )
    if futures_symbols:
        logger.info("  Futures (%d): %s", len(futures_symbols), ", ".join(futures_symbols))
    if spot_symbols:
        logger.info("  Spot    (%d): %s", len(spot_symbols), ", ".join(spot_symbols))

    store = QuoteStore(db_path=settings.db_path)
    await store.init_db()

    ws_clients: list[BinanceWSClient] = []
    if futures_symbols:
        ws_clients.append(BinanceWSClient(
            symbols=futures_symbols,
            ws_url=settings.futures_ws_url,
            store=store,
            label="futures",
        ))
    if spot_symbols:
        ws_clients.append(BinanceWSClient(
            symbols=spot_symbols,
            ws_url=settings.spot_ws_url,
            store=store,
            label="spot",
        ))

    app = create_app(store)
    uvi_config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
        loop="none",
    )
    server = uvicorn.Server(uvi_config)
    server.install_signal_handlers = lambda: None

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown() -> None:
        if stop_event.is_set():
            return
        logger.info("Shutdown signal received")
        for client in ws_clients:
            client.stop()
        server.should_exit = True
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    batch_interval_s = settings.batch_interval_ms / 1000.0

    try:
        async with asyncio.TaskGroup() as tg:
            for client in ws_clients:
                tg.create_task(client.run())
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

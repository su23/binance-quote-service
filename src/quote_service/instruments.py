"""Fetch top instruments by market capitalization from Binance."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

# Binance USD-M Futures REST endpoint
FUTURES_BASE = "https://fapi.binance.com"
TICKER_24H = "/fapi/v1/ticker/24hr"


async def fetch_top_instruments(
    n: int = 10,
    base_url: str = FUTURES_BASE,
) -> list[str]:
    """Fetch top N perpetual futures instruments by 24h quote volume.

    Uses 24h quote volume as a proxy for market capitalization — the most
    liquid, highest-cap instruments have the largest trading volume.

    Returns uppercase symbol strings like ["BTCUSDT", "ETHUSDT", ...].
    """
    url = urljoin(base_url, TICKER_24H)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        tickers = resp.json()

    tickers.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)

    top = [t["symbol"] for t in tickers[:n]]
    logger.info("Top %d instruments by volume: %s", n, ", ".join(top))
    return top

"""Fetch top instruments by market capitalization from Binance."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

SPOT_BASE = "https://api.binance.com"
SPOT_TICKER_24H = "/api/v3/ticker/24hr"


async def fetch_top_instruments(
    n: int = 10,
    base_url: str = SPOT_BASE,
) -> list[str]:
    """Fetch top N spot instruments by estimated market cap.

    Uses quoteVolume weighted by lastPrice from the spot 24hr ticker as
    a proxy for market capitalization.  Spot volumes (unlike futures) are
    not inflated by leverage, so the ranking better reflects real market
    cap ordering.

    Returns uppercase symbol strings like ["BTCUSDT", "ETHUSDT", ...].
    """
    url = f"{base_url}{SPOT_TICKER_24H}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        tickers = resp.json()

    # quoteVolume * lastPrice gives a value proportional to
    # (avg price * volume * current price), which correlates with
    # market cap better than raw quoteVolume alone.
    for t in tickers:
        t["_score"] = float(t["quoteVolume"]) * float(t["lastPrice"])

    tickers.sort(key=lambda t: t["_score"], reverse=True)

    top = [t["symbol"] for t in tickers[:n]]
    logger.info("Top %d instruments by estimated market cap: %s", n, ", ".join(top))
    return top

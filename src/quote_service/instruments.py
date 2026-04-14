"""Fetch top instruments by market capitalization from Binance."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BINANCE_MARKET_CAP_URL = (
    "https://www.binance.com/bapi/apex/v1/friendly/apex/marketing/complianceSymbolList"
)
BINANCE_FUTURES_EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"

async def fetch_top_instruments(
    n: int = 10,
    base_url: str = BINANCE_MARKET_CAP_URL,
) -> list[str]:
    """Fetch top N instruments ranked by market capitalization.

    Uses Binance's internal market data API which provides actual market
    cap (circulating supply * price) for each listed asset.

    Returns uppercase symbol strings like ``["BTCUSDT", "ETHUSDT", ...]``.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(base_url)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data", [])

    # Filter and sort by marketCap descending.
    scored: list[tuple[str, float]] = []
    for item in items:
        symbol = item.get("symbol", "")
        market_cap = float(item.get("marketCap", 0))
        if not symbol or market_cap <= 0:
            continue
        scored.append((symbol, market_cap))

    scored.sort(key=lambda x: x[1], reverse=True)

    display = max(n, 20)
    logger.info("Top %d instruments by market cap (selecting %d):", display, n)
    for i, (sym, mcap) in enumerate(scored[:display], 1):
        marker = " *" if i <= n else ""
        logger.info("  %2d. %-12s mcap=$%.2e%s", i, sym, mcap, marker)

    top = [sym for sym, _mcap in scored[:n]]
    return top


async def fetch_futures_symbols(
    base_url: str = BINANCE_FUTURES_EXCHANGE_INFO,
) -> set[str]:
    """Fetch the set of symbols available on Binance USD-M Futures.

    Returns uppercase symbol strings like ``{"BTCUSDT", "ETHUSDT", ...}``.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(base_url)
        resp.raise_for_status()
        data = resp.json()

    return {
        s["symbol"]
        for s in data.get("symbols", [])
        if s.get("status") == "TRADING" and s.get("contractType") == "PERPETUAL"
    }

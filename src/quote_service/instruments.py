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
    cap (circulating supply * price) for each listed asset.  Results are
    deduplicated by base asset.

    Returns uppercase symbol strings like ``["BTCUSDT", "ETHUSDT", ...]``.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(base_url)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data", [])

    # Filter and sort by marketCap descending.
    scored: list[tuple[str, str, float]] = []
    for item in items:
        symbol = item.get("symbol", "")
        base = item.get("baseAsset", "")
        market_cap = float(item.get("marketCap", 0))
        if not symbol or market_cap <= 0:
            continue
        scored.append((symbol, base, market_cap))

    scored.sort(key=lambda x: x[2], reverse=True)

    # Deduplicate by base asset — keep the highest-cap entry.
    seen_bases: set[str] = set()
    deduped: list[tuple[str, str, float]] = []
    for sym, base, mcap in scored:
        if base in seen_bases:
            continue
        seen_bases.add(base)
        deduped.append((sym, base, mcap))

    display = max(n, 20)
    logger.info("Top %d instruments by market cap (selecting %d):", display, n)
    for i, (sym, _base, mcap) in enumerate(deduped[:display], 1):
        marker = " *" if i <= n else ""
        logger.info("  %2d. %-12s mcap=$%.2e%s", i, sym, mcap, marker)

    top = [sym for sym, _base, _mcap in deduped[:n]]
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

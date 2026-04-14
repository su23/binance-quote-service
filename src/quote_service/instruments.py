"""Fetch top instruments by market capitalization from Binance."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BINANCE_MARKET_CAP_URL = (
    "https://www.binance.com/bapi/apex/v1/friendly/apex/marketing/complianceSymbolList"
)

# Stablecoins and wrapped assets to exclude from ranking.
_EXCLUDED_BASES = frozenset({
    "USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USD",
    "U", "USD1", "RLUSD", "USDP", "GUSD", "FRAX", "USDS",
    "WBTC", "WBETH",
})


async def fetch_top_instruments(
    n: int = 10,
    base_url: str = BINANCE_MARKET_CAP_URL,
) -> list[str]:
    """Fetch top N instruments ranked by market capitalization.

    Uses Binance's internal market data API which provides actual market
    cap (circulating supply * price) for each listed asset.  Results are
    filtered to exclude stablecoins and wrapped assets, then deduplicated
    by base asset.

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
        if base in _EXCLUDED_BASES:
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

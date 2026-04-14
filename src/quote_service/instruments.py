"""Fetch top instruments by market capitalization from Binance.

Uses the spot API to get 24h ticker data and exchange info.  All quote
volumes and prices are normalised to USD via FX rates derived from
Binance's own trading pairs so that fiat and crypto-quoted pairs are
ranked on a common basis.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

SPOT_BASE = "https://api.binance.com"
SPOT_TICKER_24H = "/api/v3/ticker/24hr"
EXCHANGE_INFO = "/api/v3/exchangeInfo"

# Stablecoins pegged ~1:1 to USD — no FX lookup needed.
_USD_STABLECOINS = frozenset({"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USD"})


def _build_usd_rates(
    tickers: list[dict],
    symbol_info: dict[str, tuple[str, str]],
) -> dict[str, float]:
    """Build a mapping of quote asset → USD rate.

    Uses three sources (in priority order):
    1. Stablecoins: hardcoded as 1.0
    2. Crypto assets: XXXUSDT price (e.g. BTC → 67 000)
    3. Fiat currencies: 1 / USDTXXX price (e.g. IDR → 1/15 700)
    """
    rates: dict[str, float] = {s: 1.0 for s in _USD_STABLECOINS}

    price_by_symbol: dict[str, float] = {}
    for t in tickers:
        try:
            price_by_symbol[t["symbol"]] = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue

    # Collect every quote asset we need a rate for.
    all_quote_assets: set[str] = set()
    for _base, quote in symbol_info.values():
        all_quote_assets.add(quote)

    for asset in all_quote_assets:
        if asset in rates:
            continue

        # Try XXXUSDT (e.g. BTCUSDT → gives BTC price in USD)
        usdt_pair = f"{asset}USDT"
        if usdt_pair in price_by_symbol:
            rates[asset] = price_by_symbol[usdt_pair]
            continue

        # Try USDTXXX (e.g. USDTIDR → 1 USDT = X IDR → 1 IDR = 1/X USD)
        fiat_pair = f"USDT{asset}"
        if fiat_pair in price_by_symbol and price_by_symbol[fiat_pair] > 0:
            rates[asset] = 1.0 / price_by_symbol[fiat_pair]
            continue

        logger.debug("No USD rate found for quote asset %s, skipping its pairs", asset)

    return rates


async def fetch_top_instruments(
    n: int = 10,
    base_url: str = SPOT_BASE,
) -> list[str]:
    """Fetch top N spot instruments ranked by estimated market cap.

    All pairs are normalised to USD using FX rates derived from Binance's
    own trading pairs.  The score for each instrument is::

        score = quoteVolume_USD * lastPrice_USD

    where ``_USD`` means the value converted to US dollars.

    Returns uppercase symbol strings like ``["BTCUSDT", "ETHUSDT", ...]``.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        ticker_resp, info_resp = await _fetch_parallel(client, base_url)

    tickers = ticker_resp.json()
    exchange_info = info_resp.json()

    # symbol → (baseAsset, quoteAsset)
    symbol_info: dict[str, tuple[str, str]] = {
        s["symbol"]: (s["baseAsset"], s["quoteAsset"])
        for s in exchange_info.get("symbols", [])
        if s.get("status") == "TRADING"
    }

    rates = _build_usd_rates(tickers, symbol_info)

    scored: list[tuple[str, float]] = []
    for t in tickers:
        sym = t["symbol"]
        if sym not in symbol_info:
            continue
        _base, quote = symbol_info[sym]
        usd_per_quote = rates.get(quote)
        if usd_per_quote is None:
            continue
        try:
            quote_volume = float(t["quoteVolume"])
            last_price = float(t["lastPrice"])
        except (KeyError, ValueError):
            continue
        # Normalise both factors to USD.
        score = (quote_volume * usd_per_quote) * (last_price * usd_per_quote)
        scored.append((sym, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    display = max(n, 20)
    logger.info("Top %d instruments by estimated market cap (selecting %d):", display, n)
    for i, (sym, score) in enumerate(scored[:display], 1):
        marker = " *" if i <= n else ""
        logger.info("  %2d. %-15s score=%.3e%s", i, sym, score, marker)

    top = [sym for sym, _score in scored[:n]]
    return top


async def _fetch_parallel(
    client: httpx.AsyncClient,
    base_url: str,
) -> tuple[httpx.Response, httpx.Response]:
    """Fetch ticker and exchange-info endpoints concurrently."""
    import asyncio

    ticker_url = f"{base_url}{SPOT_TICKER_24H}"
    info_url = f"{base_url}{EXCHANGE_INFO}"

    ticker_coro = client.get(ticker_url)
    info_coro = client.get(info_url)

    ticker_resp, info_resp = await asyncio.gather(ticker_coro, info_coro)
    ticker_resp.raise_for_status()
    info_resp.raise_for_status()
    return ticker_resp, info_resp

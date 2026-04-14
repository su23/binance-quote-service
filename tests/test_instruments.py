from __future__ import annotations

import httpx
import pytest

from quote_service.instruments import fetch_top_instruments


def _fake_exchange_info() -> dict:
    """Minimal exchangeInfo with base/quote asset metadata."""
    symbols = [
        ("BTCUSDT",  "BTC",  "USDT"),
        ("ETHUSDT",  "ETH",  "USDT"),
        ("BNBUSDT",  "BNB",  "USDT"),
        ("SOLUSDT",  "SOL",  "USDT"),
        ("XRPUSDT",  "XRP",  "USDT"),
        ("DOGEUSDT", "DOGE", "USDT"),
        ("BTCIDR",   "BTC",  "IDR"),
        ("ETHBTC",   "ETH",  "BTC"),
        ("USDTIDR",  "USDT", "IDR"),   # used to derive IDR→USD rate
        ("BTCJPY",   "BTC",  "JPY"),   # no JPY rate available → skipped
    ]
    return {
        "symbols": [
            {"symbol": sym, "baseAsset": base, "quoteAsset": quote, "status": "TRADING"}
            for sym, base, quote in symbols
        ]
    }


def _fake_tickers() -> list[dict]:
    """Fake 24hr ticker data with realistic numbers."""
    return [
        {"symbol": "BTCUSDT",  "quoteVolume": "50000000000",      "lastPrice": "67000"},
        {"symbol": "ETHUSDT",  "quoteVolume": "20000000000",      "lastPrice": "3500"},
        {"symbol": "BNBUSDT",  "quoteVolume": "5000000000",       "lastPrice": "600"},
        {"symbol": "SOLUSDT",  "quoteVolume": "4000000000",       "lastPrice": "150"},
        {"symbol": "XRPUSDT",  "quoteVolume": "3500000000",       "lastPrice": "0.55"},
        {"symbol": "DOGEUSDT", "quoteVolume": "2000000000",       "lastPrice": "0.15"},
        # BTCIDR: moderate IDR volume (1 USD ≈ 15700 IDR)
        {"symbol": "BTCIDR",   "quoteVolume": "500000000000000",  "lastPrice": "1052900000"},
        # ETHBTC: small volume in BTC terms
        {"symbol": "ETHBTC",   "quoteVolume": "5000",             "lastPrice": "0.0522"},
        # FX pair for rate derivation
        {"symbol": "USDTIDR",  "quoteVolume": "100000000",        "lastPrice": "15700"},
    ]


def _setup_mocks(httpx_mock):
    """Register both ticker and exchangeInfo responses."""
    httpx_mock.add_response(json=_fake_tickers())
    httpx_mock.add_response(json=_fake_exchange_info())


class TestFetchTopInstruments:
    @pytest.mark.asyncio
    async def test_returns_top_n(self, httpx_mock):
        _setup_mocks(httpx_mock)
        result = await fetch_top_instruments(n=6, base_url="https://fake.api")
        assert len(result) == 6
        # BTCUSDT should be at or near the top
        assert "BTCUSDT" in result[:2]
        assert "ETHUSDT" in result[:3]

    @pytest.mark.asyncio
    async def test_fiat_pairs_normalised(self, httpx_mock):
        """BTCIDR should not outrank all USDT pairs after USD normalisation."""
        _setup_mocks(httpx_mock)
        result = await fetch_top_instruments(n=10, base_url="https://fake.api")
        # BTCIDR should be roughly in the same tier as BTCUSDT (both are BTC),
        # not at the very top dominating everything
        assert result[0] in ("BTCUSDT", "BTCIDR")
        # ETHUSDT should still rank above low-cap coins
        eth_idx = result.index("ETHUSDT")
        doge_idx = result.index("DOGEUSDT")
        assert eth_idx < doge_idx

    @pytest.mark.asyncio
    async def test_crypto_quote_normalised(self, httpx_mock):
        """ETHBTC volume should be normalised via BTC→USD rate."""
        _setup_mocks(httpx_mock)
        result = await fetch_top_instruments(n=10, base_url="https://fake.api")
        # ETHBTC has 5000 BTC volume × $67k = $335M USD volume, which is
        # significant after normalisation — it should appear in results
        assert "ETHBTC" in result
        # But should rank below the major USDT pairs
        eth_btc_idx = result.index("ETHBTC")
        assert eth_btc_idx > result.index("BTCUSDT")
        assert eth_btc_idx > result.index("ETHUSDT")

    @pytest.mark.asyncio
    async def test_missing_fx_rate_skipped(self, httpx_mock):
        """Pairs with unknown quote asset FX rate are excluded."""
        _setup_mocks(httpx_mock)
        result = await fetch_top_instruments(n=20, base_url="https://fake.api")
        # BTCJPY has no JPY rate source → should not appear
        assert "BTCJPY" not in result

    @pytest.mark.asyncio
    async def test_returns_fewer_if_requested(self, httpx_mock):
        _setup_mocks(httpx_mock)
        result = await fetch_top_instruments(n=3, base_url="https://fake.api")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_top_instruments(base_url="https://fake.api")

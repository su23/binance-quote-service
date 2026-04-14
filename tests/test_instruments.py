from __future__ import annotations

import httpx
import pytest

from quote_service.instruments import fetch_top_instruments


def _fake_ticker_response() -> list[dict]:
    """Generate fake spot 24hr ticker data for testing.

    score = quoteVolume * lastPrice, used as market cap proxy.
    """
    # (symbol, quoteVolume, lastPrice) → score = quoteVolume * lastPrice
    symbols = [
        ("BTCUSDT",   50_000_000_000, 67000),   # score: 3.35e15
        ("ETHUSDT",   20_000_000_000, 3500),     # score: 7.0e13
        ("BNBUSDT",    5_000_000_000, 600),      # score: 3.0e12
        ("SOLUSDT",    4_000_000_000, 150),      # score: 6.0e11
        ("XRPUSDT",    3_500_000_000, 0.55),     # score: 1.925e9
        ("DOGEUSDT",   2_000_000_000, 0.15),     # score: 3.0e8
        ("ADAUSDT",    1_500_000_000, 0.45),     # score: 6.75e8
        ("AVAXUSDT",   1_000_000_000, 35),       # score: 3.5e10
        ("DOTUSDT",      900_000_000, 7),        # score: 6.3e9
        ("LINKUSDT",     800_000_000, 15),       # score: 1.2e10
        ("MATICUSDT",    700_000_000, 0.7),      # score: 4.9e8
        ("SHIBUSDT",     600_000_000, 0.00001),  # score: 6.0e3
        # High volume but low price — should rank lower than BTCUSDT
        ("CHEAPUSDT", 60_000_000_000, 0.00001),  # score: 6.0e5
    ]
    return [
        {
            "symbol": sym,
            "quoteVolume": str(qv),
            "lastPrice": str(price),
        }
        for sym, qv, price in symbols
    ]


class TestFetchTopInstruments:
    @pytest.mark.asyncio
    async def test_returns_top_10(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=10, base_url="https://fake.api")
        assert len(result) == 10
        assert result[0] == "BTCUSDT"
        assert result[1] == "ETHUSDT"

    @pytest.mark.asyncio
    async def test_price_weighting_matters(self, httpx_mock):
        """CHEAPUSDT has highest quoteVolume but lowest score due to low price."""
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=13, base_url="https://fake.api")
        assert result[-1] == "SHIBUSDT"  # lowest score
        assert result[-2] == "CHEAPUSDT"  # high volume but near-zero price
        assert "CHEAPUSDT" not in result[:10]  # not in top 10

    @pytest.mark.asyncio
    async def test_returns_fewer_if_requested(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=3, base_url="https://fake.api")
        assert len(result) == 3
        assert result == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    @pytest.mark.asyncio
    async def test_sorted_by_score(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=5, base_url="https://fake.api")
        assert result == ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "AVAXUSDT"]

    @pytest.mark.asyncio
    async def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_top_instruments(base_url="https://fake.api")

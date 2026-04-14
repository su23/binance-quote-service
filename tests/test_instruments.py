from __future__ import annotations

import json

import httpx
import pytest

from quote_service.instruments import fetch_top_instruments


def _fake_ticker_response(n: int = 20) -> list[dict]:
    """Generate fake 24hr ticker data for testing."""
    symbols = [
        ("BTCUSDT", 50_000_000_000),
        ("ETHUSDT", 20_000_000_000),
        ("BNBUSDT", 5_000_000_000),
        ("SOLUSDT", 4_000_000_000),
        ("XRPUSDT", 3_500_000_000),
        ("DOGEUSDT", 2_000_000_000),
        ("ADAUSDT", 1_500_000_000),
        ("AVAXUSDT", 1_000_000_000),
        ("DOTUSDT", 900_000_000),
        ("LINKUSDT", 800_000_000),
        ("MATICUSDT", 700_000_000),
        ("SHIBUSDT", 600_000_000),
        ("LTCUSDT", 500_000_000),
        # Non-USDT pairs should be filtered out
        ("BTCBUSD", 40_000_000_000),
        ("ETHBTC", 10_000_000_000),
    ]
    return [
        {
            "symbol": sym,
            "quoteVolume": str(vol),
            "volume": str(vol / 50000),
            "lastPrice": "50000",
        }
        for sym, vol in symbols[:n]
    ]


class TestFetchTopInstruments:
    @pytest.mark.asyncio
    async def test_returns_top_10(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=10, base_url="https://fake.api")
        assert len(result) == 10
        assert result[0] == "BTCUSDT"
        assert result[1] == "ETHUSDT"
        # Non-USDT pairs should be excluded
        assert "BTCBUSD" not in result
        assert "ETHBTC" not in result

    @pytest.mark.asyncio
    async def test_returns_fewer_if_requested(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=3, base_url="https://fake.api")
        assert len(result) == 3
        assert result == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    @pytest.mark.asyncio
    async def test_sorted_by_volume(self, httpx_mock):
        httpx_mock.add_response(json=_fake_ticker_response())
        result = await fetch_top_instruments(n=5, base_url="https://fake.api")
        assert result == ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

    @pytest.mark.asyncio
    async def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_top_instruments(base_url="https://fake.api")

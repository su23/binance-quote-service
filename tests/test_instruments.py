from __future__ import annotations

import httpx
import pytest

from quote_service.instruments import fetch_top_instruments


def _fake_market_data() -> dict:
    """Fake Binance complianceSymbolList response."""
    items = [
        ("BTCUSDT",  1_490_000_000_000),
        ("ETHUSDT",    286_000_000_000),
        ("USDTUSD",   185_000_000_000),
        ("XRPUSDT",    84_100_000_000),
        ("BNBUSDT",    84_000_000_000),
        ("USDCUSDT",   78_700_000_000),
        ("SOLUSDT",    49_400_000_000),
        ("TRXUSDT",    32_100_000_000),
        ("DOGEUSDT",   14_500_000_000),
        ("USDSUSDT",   11_300_000_000),
        ("WBTCUSDT",    8_870_000_000),
        ("WBETHUSDT",   8_750_000_000),
        ("ADAUSDT",     8_790_000_000),
        ("XLMUSDT",     7_850_000_000),
        ("LINKUSDT",    6_200_000_000),
        ("AVAXUSDT",    5_100_000_000),
        ("DOTUSDT",     4_800_000_000),
    ]
    return {
        "code": "000000",
        "data": [
            {
                "symbol": sym,
                "marketCap": str(mcap),
            }
            for sym, mcap in items
        ],
    }


class TestFetchTopInstruments:
    @pytest.mark.asyncio
    async def test_returns_top_10(self, httpx_mock):
        httpx_mock.add_response(json=_fake_market_data())
        result = await fetch_top_instruments(n=10, base_url="https://fake.api")
        assert len(result) == 10
        assert result[0] == "BTCUSDT"
        assert result[1] == "ETHUSDT"
        assert result[2] == "USDTUSD"  # #3 by market cap

    @pytest.mark.asyncio
    async def test_includes_all_asset_types(self, httpx_mock):
        """Stablecoins and wrapped assets are legitimate instruments."""
        httpx_mock.add_response(json=_fake_market_data())
        result = await fetch_top_instruments(n=20, base_url="https://fake.api")
        assert "USDTUSD" in result
        assert "USDCUSDT" in result
        assert "WBTCUSDT" in result

    @pytest.mark.asyncio
    async def test_ranked_by_market_cap(self, httpx_mock):
        httpx_mock.add_response(json=_fake_market_data())
        result = await fetch_top_instruments(n=5, base_url="https://fake.api")
        assert result == ["BTCUSDT", "ETHUSDT", "USDTUSD", "XRPUSDT", "BNBUSDT"]

    @pytest.mark.asyncio
    async def test_returns_fewer_if_requested(self, httpx_mock):
        httpx_mock.add_response(json=_fake_market_data())
        result = await fetch_top_instruments(n=3, base_url="https://fake.api")
        assert len(result) == 3
        assert result == ["BTCUSDT", "ETHUSDT", "USDTUSD"]

    @pytest.mark.asyncio
    async def test_http_error_raises(self, httpx_mock):
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_top_instruments(base_url="https://fake.api")

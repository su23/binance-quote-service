from __future__ import annotations

import httpx
import pytest

from quote_service.instruments import fetch_top_instruments


def _fake_market_data() -> dict:
    """Fake Binance complianceSymbolList response."""
    items = [
        ("BTCUSDT",  "BTC",  1_490_000_000_000),
        ("ETHUSDT",  "ETH",    286_000_000_000),
        ("XRPUSDT",  "XRP",     84_100_000_000),
        ("BNBUSDT",  "BNB",     84_000_000_000),
        ("SOLUSDT",  "SOL",     49_400_000_000),
        ("TRXUSDT",  "TRX",     32_100_000_000),
        ("DOGEUSDT", "DOGE",    14_500_000_000),
        ("ADAUSDT",  "ADA",      8_790_000_000),
        ("XLMUSDT",  "XLM",      7_850_000_000),
        ("LINKUSDT", "LINK",     6_200_000_000),
        ("AVAXUSDT", "AVAX",     5_100_000_000),
        ("DOTUSDT",  "DOT",      4_800_000_000),
        # Stablecoins — should be excluded
        ("USDTUSD",  "USDT",  185_000_000_000),
        ("USDCUSDT", "USDC",   78_700_000_000),
        ("USDSUSDT", "USDS",   11_300_000_000),
        # Wrapped assets — should be excluded
        ("WBTCUSDT", "WBTC",    8_870_000_000),
        ("WBETHUSDT","WBETH",   8_750_000_000),
        # Duplicate base (BTC in different quote) — should be deduped
        ("BTCEUR",   "BTC",  1_400_000_000_000),
    ]
    return {
        "code": "000000",
        "data": [
            {
                "symbol": sym,
                "baseAsset": base,
                "marketCap": str(mcap),
            }
            for sym, base, mcap in items
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
    async def test_deduplicates_by_base_asset(self, httpx_mock):
        httpx_mock.add_response(json=_fake_market_data())
        result = await fetch_top_instruments(n=20, base_url="https://fake.api")
        # BTCUSDT wins over BTCEUR (higher marketCap)
        assert "BTCUSDT" in result
        assert "BTCEUR" not in result

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

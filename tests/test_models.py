from __future__ import annotations

import pytest

from quote_service.models import Quote, QuoteResponse, parse_book_ticker


def _make_raw(
    symbol: str = "BTCUSDT",
    bid: str = "50000.00",
    bid_qty: str = "1.5",
    ask: str = "50001.00",
    ask_qty: str = "2.0",
    event_time: int = 1700000000000,
) -> dict:
    return {
        "e": "bookTicker",
        "u": 1234567890,
        "E": event_time,
        "T": event_time - 1,
        "s": symbol,
        "b": bid,
        "B": bid_qty,
        "a": ask,
        "A": ask_qty,
    }


class TestParseBookTicker:
    def test_basic_parse(self):
        raw = _make_raw()
        q = parse_book_ticker(raw)
        assert q.symbol == "BTCUSDT"
        assert q.bid_price == 50000.00
        assert q.bid_size == 1.5
        assert q.ask_price == 50001.00
        assert q.ask_size == 2.0
        assert q.event_time == 1700000000000
        assert q.receive_time_ns > 0

    def test_small_prices(self):
        raw = _make_raw(bid="0.00000100", bid_qty="1000000", ask="0.00000101", ask_qty="999999")
        q = parse_book_ticker(raw)
        assert q.bid_price == pytest.approx(0.000001)
        assert q.ask_price == pytest.approx(0.00000101)

    def test_zero_size(self):
        raw = _make_raw(bid_qty="0", ask_qty="0")
        q = parse_book_ticker(raw)
        assert q.bid_size == 0.0
        assert q.ask_size == 0.0

    def test_missing_field_raises(self):
        raw = _make_raw()
        del raw["b"]
        with pytest.raises(KeyError):
            parse_book_ticker(raw)

    def test_multiple_symbols(self):
        for sym in ["ETHUSDT", "SOLUSDT", "BNBUSDT"]:
            q = parse_book_ticker(_make_raw(symbol=sym))
            assert q.symbol == sym


class TestQuoteResponse:
    def test_from_quote(self):
        q = Quote(
            symbol="ETHUSDT",
            bid_price=3000.0,
            bid_size=10.0,
            ask_price=3001.0,
            ask_size=5.0,
            event_time=1700000000000,
            receive_time_ns=123456789,
        )
        resp = QuoteResponse.from_quote(q)
        assert resp.symbol == "ETHUSDT"
        assert resp.bid_price == 3000.0
        assert resp.ask_price == 3001.0
        assert resp.event_time_ms == 1700000000000

    def test_serialization(self):
        q = Quote("X", 1.0, 2.0, 3.0, 4.0, 100, 200)
        resp = QuoteResponse.from_quote(q)
        data = resp.model_dump()
        assert set(data.keys()) == {
            "symbol",
            "bid_price",
            "bid_size",
            "ask_price",
            "ask_size",
            "event_time_ms",
            "receive_latency_us",
        }

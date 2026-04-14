"""Latency benchmarks for the hot path: parse + store update."""

import pytest

from quote_service.models import Quote, parse_book_ticker
from quote_service.store import QuoteStore

# Representative Binance futures bookTicker payload
SAMPLE_TICKER = {
    "e": "bookTicker",
    "u": 400900217,
    "E": 1700000000000,
    "T": 1700000000000,
    "s": "BTCUSDT",
    "b": "67432.50000000",
    "B": "1.23400000",
    "a": "67433.00000000",
    "A": "0.56700000",
}


@pytest.fixture
def store():
    return QuoteStore(db_path=":memory:")


def test_parse_book_ticker_latency(benchmark):
    """Measure parse_book_ticker: orjson already decoded, this is the
    float conversion + dataclass construction step."""
    result = benchmark(parse_book_ticker, SAMPLE_TICKER)
    assert result.symbol == "BTCUSDT"


def test_store_update_latency(benchmark, store):
    """Measure in-memory dict update (the hot-path write)."""
    quote = Quote(
        symbol="BTCUSDT",
        bid_price=67432.50,
        bid_size=1.234,
        ask_price=67433.00,
        ask_size=0.567,
        event_time=1700000000000,
    )
    benchmark(store.update, quote)
    assert store.get_latest("BTCUSDT") is quote


def test_parse_and_update_latency(benchmark, store):
    """Measure the full hot path: parse + store update combined."""

    def parse_and_update():
        q = parse_book_ticker(SAMPLE_TICKER)
        store.update(q)

    benchmark(parse_and_update)
    assert store.get_latest("BTCUSDT") is not None


def test_get_latest_latency(benchmark, store):
    """Measure O(1) dict lookup for latest quote."""
    quote = Quote(
        symbol="BTCUSDT",
        bid_price=67432.50,
        bid_size=1.234,
        ask_price=67433.00,
        ask_size=0.567,
        event_time=1700000000000,
    )
    store.update(quote)
    result = benchmark(store.get_latest, "BTCUSDT")
    assert result is quote


def test_get_all_latest_latency(benchmark, store):
    """Measure snapshot copy of all 10 latest quotes."""
    for i in range(10):
        store.update(Quote(
            symbol=f"SYM{i}USDT",
            bid_price=100.0 + i,
            bid_size=1.0,
            ask_price=100.5 + i,
            ask_size=1.0,
            event_time=1700000000000,
        ))
    result = benchmark(store.get_all_latest)
    assert len(result) == 10

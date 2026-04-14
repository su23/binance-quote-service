from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(slots=True)
class Quote:
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    event_time: int  # Binance event timestamp (ms)
    receive_time_ns: int  # local monotonic_ns at receive


def parse_book_ticker(data: dict) -> Quote:
    """Parse a Binance futures bookTicker message into a Quote.

    Expected fields (futures combined-stream payload):
        s  - symbol
        b  - best bid price
        B  - best bid qty
        a  - best ask price
        A  - best ask qty
        E  - event time (ms)
    """
    return Quote(
        symbol=data["s"],
        bid_price=float(data["b"]),
        bid_size=float(data["B"]),
        ask_price=float(data["a"]),
        ask_size=float(data["A"]),
        event_time=int(data["E"]),
        receive_time_ns=time.monotonic_ns(),
    )


class QuoteResponse(BaseModel):
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    event_time_ms: int
    receive_latency_us: float  # processing latency in microseconds

    @classmethod
    def from_quote(cls, q: Quote, ref_time_ns: int | None = None) -> QuoteResponse:
        return cls(
            symbol=q.symbol,
            bid_price=q.bid_price,
            bid_size=q.bid_size,
            ask_price=q.ask_price,
            ask_size=q.ask_size,
            event_time_ms=q.event_time,
            receive_latency_us=0.0,  # not meaningful for stored quotes
        )

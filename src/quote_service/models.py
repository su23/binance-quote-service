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
    event_time: int  # timestamp in ms


def parse_book_ticker(data: dict) -> Quote:
    """Parse a Binance bookTicker message into a Quote.

    Works with both spot and futures payloads:
        s  - symbol
        b  - best bid price
        B  - best bid qty
        a  - best ask price
        A  - best ask qty
        E  - event time (ms) — present on futures, absent on spot

    When E is missing (spot), uses the current wall-clock time.
    """
    return Quote(
        symbol=data["s"],
        bid_price=float(data["b"]),
        bid_size=float(data["B"]),
        ask_price=float(data["a"]),
        ask_size=float(data["A"]),
        event_time=data.get("E") or int(time.time() * 1000),
    )


class QuoteResponse(BaseModel):
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    event_time_ms: int

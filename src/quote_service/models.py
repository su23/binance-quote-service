from __future__ import annotations

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


def parse_book_ticker(data: dict) -> Quote:
    """Parse a Binance futures bookTicker message into a Quote.

    Expected fields (futures combined-stream payload):
        s  - symbol
        b  - best bid price
        B  - best bid qty
        a  - best ask price
        A  - best ask qty
        E  - event time (ms, already int from orjson)
    """
    return Quote(
        symbol=data["s"],
        bid_price=float(data["b"]),
        bid_size=float(data["B"]),
        ask_price=float(data["a"]),
        ask_size=float(data["A"]),
        event_time=data["E"],
    )


class QuoteResponse(BaseModel):
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    event_time_ms: int

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Query

from .models import Quote, QuoteResponse
from .store import QuoteStore

def _quote_to_dict(q: Quote) -> dict:
    return {
        "symbol": q.symbol,
        "bid_price": q.bid_price,
        "bid_size": q.bid_size,
        "ask_price": q.ask_price,
        "ask_size": q.ask_size,
        "event_time_ms": q.event_time,
    }


def create_app(store: QuoteStore) -> FastAPI:
    app = FastAPI(title="Binance Quote Service")
    start_time = time.monotonic()

    @app.get("/quotes", response_model=list[QuoteResponse])
    async def get_all_quotes() -> list[dict]:
        return [_quote_to_dict(q) for q in store.get_all_latest().values()]

    @app.get("/quotes/{symbol}", response_model=QuoteResponse)
    async def get_quote(symbol: str) -> dict:
        q = store.get_latest(symbol)
        if q is None:
            raise HTTPException(status_code=404, detail=f"No quote for {symbol.upper()}")
        return _quote_to_dict(q)

    @app.get("/quotes/{symbol}/history", response_model=list[QuoteResponse])
    async def get_history(
        symbol: str,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict]:
        return await store.get_history(symbol, limit=limit)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "symbols_active": len(store.get_all_latest()),
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }

    return app

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException

from .models import QuoteResponse
from .store import QuoteStore

_start_time = time.monotonic()


def create_app(store: QuoteStore) -> FastAPI:
    app = FastAPI(title="Binance Quote Service")

    @app.get("/quotes", response_model=list[QuoteResponse])
    async def get_all_quotes() -> list[QuoteResponse]:
        latest = store.get_all_latest()
        return [QuoteResponse.from_quote(q) for q in latest.values()]

    @app.get("/quotes/{symbol}", response_model=QuoteResponse)
    async def get_quote(symbol: str) -> QuoteResponse:
        q = store.get_latest(symbol)
        if q is None:
            raise HTTPException(status_code=404, detail=f"No quote for {symbol.upper()}")
        return QuoteResponse.from_quote(q)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "symbols_active": len(store.get_all_latest()),
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
        }

    return app

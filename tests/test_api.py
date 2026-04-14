from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from quote_service.api import create_app
from quote_service.models import Quote
from quote_service.store import QuoteStore


def _quote(symbol: str = "BTCUSDT", bid: float = 50000.0, ask: float = 50001.0) -> Quote:
    return Quote(symbol, bid, 1.0, ask, 1.0, 1700000000000)


@pytest.fixture
def app(store: QuoteStore):
    return create_app(store)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert data["symbols_active"] == 0


class TestGetAllQuotes:
    @pytest.mark.asyncio
    async def test_empty(self, client: AsyncClient):
        resp = await client.get("/quotes")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_with_quotes(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote("BTCUSDT"))
        store.update(_quote("ETHUSDT", 3000.0, 3001.0))
        resp = await client.get("/quotes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        symbols = {q["symbol"] for q in data}
        assert symbols == {"BTCUSDT", "ETHUSDT"}

    @pytest.mark.asyncio
    async def test_response_schema(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote())
        resp = await client.get("/quotes")
        q = resp.json()[0]
        assert "bid_price" in q
        assert "bid_size" in q
        assert "ask_price" in q
        assert "ask_size" in q
        assert "event_time_ms" in q


class TestGetSingleQuote:
    @pytest.mark.asyncio
    async def test_existing_symbol(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote("BTCUSDT"))
        resp = await client.get("/quotes/BTCUSDT")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote("BTCUSDT"))
        resp = await client.get("/quotes/btcusdt")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient):
        resp = await client.get("/quotes/NONEXIST")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_quote_values(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote("BTCUSDT", bid=49999.50, ask=50000.50))
        resp = await client.get("/quotes/BTCUSDT")
        data = resp.json()
        assert data["bid_price"] == 49999.50
        assert data["ask_price"] == 50000.50


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_history_returns_persisted_quotes(self, client: AsyncClient, store: QuoteStore):
        store.update(_quote("BTCUSDT", bid=50000.0, ask=50001.0))
        store.update(_quote("BTCUSDT", bid=50010.0, ask=50011.0))
        await store.flush()
        resp = await client.get("/quotes/BTCUSDT/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_history_not_found(self, client: AsyncClient):
        resp = await client.get("/quotes/NONEXIST/history")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_history_limit(self, client: AsyncClient, store: QuoteStore):
        for i in range(5):
            store.update(Quote("BTCUSDT", 50000.0 + i, 1.0, 50001.0 + i, 1.0, 1700000000000 + i))
        await store.flush()
        resp = await client.get("/quotes/BTCUSDT/history?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_history_limit_validation(self, client: AsyncClient):
        resp = await client.get("/quotes/BTCUSDT/history?limit=0")
        assert resp.status_code == 422
        resp = await client.get("/quotes/BTCUSDT/history?limit=1001")
        assert resp.status_code == 422

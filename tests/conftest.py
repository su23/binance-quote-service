from __future__ import annotations

import pytest
import pytest_asyncio

from quote_service.config import Settings
from quote_service.store import QuoteStore


@pytest_asyncio.fixture
async def store(tmp_path):
    """QuoteStore backed by a temporary SQLite database."""
    db_path = str(tmp_path / "test.db")
    s = QuoteStore(db_path=db_path, batch_size=10)
    await s.init_db()
    yield s
    await s.close()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        symbols=["BTCUSDT", "ETHUSDT"],
        db_path=str(tmp_path / "test.db"),
        api_port=0,
    )

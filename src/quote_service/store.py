from __future__ import annotations

import logging
from typing import Sequence

import aiosqlite

from .models import Quote

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS quotes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT    NOT NULL,
    bid_price REAL    NOT NULL,
    bid_size  REAL    NOT NULL,
    ask_price REAL    NOT NULL,
    ask_size  REAL    NOT NULL,
    event_time_ms INTEGER NOT NULL,
    inserted_at   INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_quotes_symbol_time
ON quotes (symbol, event_time_ms);
"""

_INSERT = """
INSERT INTO quotes (symbol, bid_price, bid_size, ask_price, ask_size, event_time_ms)
VALUES (?, ?, ?, ?, ?, ?);
"""


class QuoteStore:
    """In-memory latest quotes + SQLite persistence with batched writes."""

    def __init__(self, db_path: str = "quotes.db", batch_size: int = 50) -> None:
        self._db_path = db_path
        self._batch_size = batch_size
        self._latest: dict[str, Quote] = {}
        self._buffer: list[Quote] = []
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA synchronous=NORMAL;")
        await self._db.execute(_CREATE_TABLE)
        await self._db.execute(_CREATE_INDEX)
        await self._db.commit()

    def update(self, quote: Quote) -> None:
        """Update in-memory latest quote and buffer for DB write."""
        self._latest[quote.symbol] = quote
        self._buffer.append(quote)

    async def flush(self) -> int:
        """Flush buffered quotes to SQLite. Returns number of rows written.

        Safe without a lock: update() is synchronous (no await), so the
        reference swap below executes atomically within the event loop —
        no coroutine can interleave between the two assignments.
        """
        if not self._buffer:
            return 0

        # Single-expression swap: grabs the old list and replaces it
        # with a new empty one in one statement — no way for update()
        # to interleave, even if an await were somehow added nearby.
        to_write, self._buffer = self._buffer, []

        if self._db is None:
            raise RuntimeError("QuoteStore.init_db() must be called before use")
        await self._db.executemany(
            _INSERT,
            ((q.symbol, q.bid_price, q.bid_size, q.ask_price, q.ask_size, q.event_time)
             for q in to_write),
        )
        await self._db.commit()
        return len(to_write)

    def get_latest(self, symbol: str) -> Quote | None:
        return self._latest.get(symbol.upper())

    def get_all_latest(self) -> dict[str, Quote]:
        return dict(self._latest)

    async def get_history(
        self, symbol: str, limit: int = 100
    ) -> Sequence[dict]:
        """Fetch recent quotes from SQLite for a symbol."""
        if self._db is None:
            raise RuntimeError("QuoteStore.init_db() must be called before use")
        cursor = await self._db.execute(
            "SELECT symbol, bid_price, bid_size, ask_price, ask_size, event_time_ms "
            "FROM quotes WHERE symbol = ? ORDER BY event_time_ms DESC LIMIT ?",
            (symbol.upper(), limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "symbol": r[0],
                "bid_price": r[1],
                "bid_size": r[2],
                "ask_price": r[3],
                "ask_size": r[4],
                "event_time_ms": r[5],
            }
            for r in rows
        ]

    async def close(self) -> None:
        await self.flush()
        if self._db:
            await self._db.close()

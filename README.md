# Binance Quote Service

Real-time streaming quote service for the top 10 Binance instruments by market capitalization.

Connects to Binance WebSocket APIs (USD-M Futures where available, Spot for the rest), streams best bid/ask (bookTicker) data, persists quotes to SQLite, and serves the latest quotes via a REST API.

## Architecture

```
Binance USD-M Futures        websockets            orjson.loads
  wss://fstream.binance.com ──────────┐
  (bookTicker)                        ├──> WS Client(s) ──────────> store.update()
Binance Spot                          │                                  │
  wss://stream.binance.com:9443 ──────┘                       ┌─────────┴─────────┐
                                                              ▼                   ▼
                                                        In-Memory Dict      SQLite (WAL)
                                                        (latest quotes)   (periodic flush)
                                                              │
                                                              ▼
                                                        FastAPI REST API
```

- **WebSocket client** connects to Binance combined bookTicker stream with auto-reconnect and exponential backoff
- **In-memory dict** stores the latest quote per symbol for O(1) reads
- **SQLite (WAL mode)** persists all quotes with batched writes for I/O efficiency
- **FastAPI** serves the REST API with auto-generated OpenAPI docs
- At startup, the top 10 instruments are **automatically discovered** from the Binance market data API, ranked by market capitalization (circulating supply × price)

### Performance

The hot path (WS message arrival to quote availability) is fully synchronous with zero async context switches:

```
WS recv → orjson.loads → parse_book_ticker (4x float()) → dict[symbol] = quote
```

- **orjson** for JSON parsing (~3-5x faster than stdlib `json`)
- **No queue, no lock** — WS client updates the store directly via a synchronous `update()` call
- **No intermediate allocations** — buffer swap in `flush()` is a single atomic expression
- DB writes happen in a **background periodic flush**, completely off the hot path

## Prerequisites

- Python 3.11+
- pip

## Install

```bash
pip install -e ".[dev]"
```

## Run

### Docker

```bash
docker build -t quote-service .

# Run with persistent storage (quotes survive container restarts)
docker run -p 8000:8000 -v $(pwd)/data:/data quote-service

# Or without persistence (data lost on container stop)
docker run -p 8000:8000 quote-service
```

### Local

```bash
# With auto-discovered top 10 instruments (default)
quote-service

# Or via python module
python -m quote_service.main

# With custom symbols
QS_SYMBOLS='["BTCUSDT","ETHUSDT","SOLUSDT"]' quote-service
```

The REST API starts on `http://0.0.0.0:8000` by default.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /quotes` | Latest quotes for all tracked instruments |
| `GET /quotes/{symbol}` | Latest quote for a specific symbol (e.g., `/quotes/BTCUSDT`) |
| `GET /quotes/{symbol}/history?limit=100` | Recent quote history from SQLite (1–1000, default 100) |
| `GET /health` | Service health check with active symbol count and uptime |
| `GET /docs` | Interactive OpenAPI documentation (Swagger UI) |

### Example response

```json
{
  "symbol": "BTCUSDT",
  "bid_price": 67432.50,
  "bid_size": 1.234,
  "ask_price": 67433.00,
  "ask_size": 0.567,
  "event_time_ms": 1700000000000
}
```

## Configuration

All settings are configured via environment variables with the `QS_` prefix:

| Variable | Default | Description |
|---|---|---|
| `QS_SYMBOLS` | `[]` (auto-discover) | JSON list of symbols to track. Empty = auto-discover top N from Binance |
| `QS_NUM_INSTRUMENTS` | `10` | Number of top instruments to discover (when symbols is empty) |
| `QS_DB_PATH` | `quotes.db` | SQLite database file path |
| `QS_API_HOST` | `0.0.0.0` | API server host |
| `QS_API_PORT` | `8000` | API server port |
| `QS_BATCH_SIZE` | `50` | Max quotes per DB batch write |
| `QS_BATCH_INTERVAL_MS` | `100` | DB flush interval in milliseconds |
| `QS_SPOT_WS_URL` | `wss://stream.binance.com:9443` | Binance Spot WebSocket URL |
| `QS_FUTURES_WS_URL` | `wss://fstream.binance.com` | Binance USD-M Futures WebSocket URL |
| `QS_FUTURES_REST_URL` | `https://fapi.binance.com` | Binance Futures REST API URL (for symbol discovery) |

## Test

```bash
# Run all tests
pytest -v

# Run specific test module
pytest tests/test_store.py -v

# Run with coverage
pytest --cov=quote_service -v

# Run latency benchmarks
pytest tests/test_benchmark.py -v
```

CI runs automatically on push/PR to `main` via GitHub Actions (see `.github/workflows/ci.yml`), testing Python 3.11–3.13 with a 90% coverage gate.

## Limitations

- **SQLite is single-node only.** The WAL-mode SQLite database supports concurrent reads from the API while the flush loop writes, but it does not support multi-process or distributed deployments. For horizontal scaling, swap to PostgreSQL or another networked database.

## Project Structure

```
src/quote_service/
├── main.py          # Entry point: starts WS client, flush loop, API server
├── config.py        # Settings via pydantic-settings (env vars)
├── instruments.py   # Auto-discovers top instruments from Binance REST API
├── ws_client.py     # Binance WebSocket client with auto-reconnect
├── store.py         # In-memory dict + SQLite persistence with batched writes
├── api.py           # FastAPI REST endpoints
└── models.py        # Quote dataclass and Pydantic response models
```

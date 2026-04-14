# Binance Quote Service

Real-time streaming quote service for the top 10 Binance perpetual futures instruments by market capitalization.

Connects to Binance USD-M Futures WebSocket API, streams best bid/ask (bookTicker) data, persists quotes to SQLite, and serves the latest quotes via a REST API.

## Architecture

```
Binance USD-M Futures        websockets         asyncio.Queue
  wss://fstream.binance.com ──────────> WS Client ──────────> Quote Processor
  (bookTicker x 10 symbols)                                       │
                                                       ┌──────────┴──────────┐
                                                       ▼                     ▼
                                                 In-Memory Dict         SQLite (WAL)
                                                 (latest quotes)        (all quotes)
                                                       │
                                                       ▼
                                                 FastAPI REST API
```

- **WebSocket client** connects to Binance combined bookTicker stream with auto-reconnect
- **In-memory dict** stores the latest quote per symbol for O(1) reads
- **SQLite (WAL mode)** persists all quotes with batched writes for I/O efficiency
- **FastAPI** serves the REST API with auto-generated OpenAPI docs
- At startup, the top 10 instruments are **automatically discovered** from Binance by 24h trading volume (proxy for market cap)

## Prerequisites

- Python 3.11+
- pip

## Install

```bash
pip install -e ".[dev]"
```

## Run

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
  "event_time_ms": 1700000000000,
  "receive_latency_us": 0.0
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
| `QS_WS_URL` | `wss://fstream.binance.com` | Binance WebSocket URL |
| `QS_REST_URL` | `https://fapi.binance.com` | Binance REST API URL (for instrument discovery) |

## Test

```bash
# Run all tests
pytest -v

# Run specific test module
pytest tests/test_store.py -v

# Run with coverage (install pytest-cov first)
pytest --cov=quote_service -v
```

## Project Structure

```
src/quote_service/
├── main.py          # Entry point: starts WS client, processor, API server
├── config.py        # Settings via pydantic-settings (env vars)
├── instruments.py   # Auto-discovers top instruments from Binance REST API
├── ws_client.py     # Binance WebSocket client with auto-reconnect
├── store.py         # In-memory dict + SQLite persistence with batched writes
├── api.py           # FastAPI REST endpoints
└── models.py        # Quote dataclass and Pydantic response models
```

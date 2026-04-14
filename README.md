# Binance Quote Service

[![CI](https://github.com/su23/binance-quote-service/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/su23/binance-quote-service/actions/workflows/ci.yml)

Real-time streaming quote service for the top 10 Binance instruments by market capitalization.

A **quote** is the current best bid/ask snapshot for an instrument: `bid_price`, `bid_size`, `ask_price`, `ask_size`.

Connects to Binance WebSocket APIs (USD-M Futures where available, Spot for the rest), streams bookTicker data, persists quotes to SQLite, and serves the latest quotes via a REST API.

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

- At startup, the top 10 instruments are **automatically discovered** from Binance's [`complianceSymbolList`](https://www.binance.com/bapi/apex/v1/friendly/apex/marketing/complianceSymbolList) endpoint, ranked by actual **market capitalization** (circulating supply × price). One pair per base asset is selected (highest market cap entry wins), and the top 20 are logged for visibility.
- For each selected instrument, the service checks whether a **USD-M Futures perpetual** exists. If so, quotes are streamed from the **Futures** WebSocket (which includes event timestamps); otherwise, the **Spot** WebSocket is used. Both streams update the same store.
- **In-memory dict** stores the latest quote per symbol for O(1) reads
- **SQLite (WAL mode)** persists all quotes with batched writes for I/O efficiency
- **FastAPI** serves the REST API with auto-generated OpenAPI docs

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

### Example startup output

```
Top 20 instruments by market cap (selecting 10):
   1. BTCUSDT      mcap=$1.49e+12 *
   2. ETHUSDT      mcap=$2.86e+11 *
   3. USDTUSD      mcap=$1.85e+11 *
   4. XRPUSDT      mcap=$8.41e+10 *
   5. BNBUSDT      mcap=$8.40e+10 *
   6. USDCUSDT     mcap=$7.87e+10 *
   7. SOLUSDT      mcap=$4.94e+10 *
   8. TRXUSDT      mcap=$3.21e+10 *
   9. DOGEUSDT     mcap=$1.45e+10 *
  10. ADAUSDT      mcap=$8.79e+09 *
  ...
Starting Binance Quote Service for 10 symbols: BTCUSDT, ETHUSDT, ...
  Futures (7): BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT, TRXUSDT, DOGEUSDT
  Spot    (3): USDTUSD, USDCUSDT, ADAUSDT
```

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

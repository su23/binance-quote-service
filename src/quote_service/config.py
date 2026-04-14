from pydantic_settings import BaseSettings

FALLBACK_SYMBOLS: list[str] = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "LINKUSDT",
]

BINANCE_SPOT_WS = "wss://stream.binance.com:9443"
BINANCE_FUTURES_WS = "wss://fstream.binance.com"
BINANCE_FUTURES_REST = "https://fapi.binance.com"


class Settings(BaseSettings):
    model_config = {"env_prefix": "QS_"}

    symbols: list[str] = []  # empty = auto-discover top 10 from Binance
    num_instruments: int = 10
    db_path: str = "quotes.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    batch_interval_ms: int = 100
    spot_ws_url: str = BINANCE_SPOT_WS
    futures_ws_url: str = BINANCE_FUTURES_WS
    futures_rest_url: str = BINANCE_FUTURES_REST

"""
Global configuration settings for the Options Trading System.
Loads from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — env vars can be set manually


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", "sqlite:///./trading.db"
    ))
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


@dataclass
class RedisConfig:
    """Redis cache configuration."""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = 0
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    ttl: int = 300  # default TTL in seconds


@dataclass
class ZerodhaConfig:
    """Zerodha Kite API credentials."""
    api_key: str = field(default_factory=lambda: os.getenv("ZERODHA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("ZERODHA_API_SECRET", ""))
    access_token: Optional[str] = field(
        default_factory=lambda: os.getenv("ZERODHA_ACCESS_TOKEN")
    )
    request_token: Optional[str] = field(
        default_factory=lambda: os.getenv("ZERODHA_REQUEST_TOKEN")
    )


@dataclass
class UpstoxConfig:
    """Upstox API v2 credentials."""
    api_key: str = field(default_factory=lambda: os.getenv("UPSTOX_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("UPSTOX_API_SECRET", ""))
    redirect_uri: str = field(
        default_factory=lambda: os.getenv("UPSTOX_REDIRECT_URI", "https://127.0.0.1/")
    )
    access_token: Optional[str] = field(
        default_factory=lambda: os.getenv("UPSTOX_ACCESS_TOKEN")
    )
    rtoken: Optional[str] = field(
        default_factory=lambda: os.getenv("UPSTOX_RTOKEN")  # refresh token
    )


@dataclass
class RiskConfig:
    """Global risk management parameters."""
    max_daily_loss_pct: float = 2.0           # % of capital
    max_position_size_pct: float = 5.0        # % of capital per trade
    max_open_positions: int = 5
    default_stop_loss_pct: float = 30.0       # % of option premium
    default_target_pct: float = 50.0          # % of option premium
    trailing_stop_activation_pct: float = 20.0
    trailing_stop_pct: float = 10.0
    max_slippage_pct: float = 0.5


@dataclass
class TradingConfig:
    """Core trading parameters."""
    broker: str = field(default_factory=lambda: os.getenv("BROKER", "zerodha"))
    paper_trading: bool = field(
        default_factory=lambda: os.getenv("PAPER_TRADING", "true").lower() == "true"
    )
    capital: float = field(
        default_factory=lambda: float(os.getenv("TRADING_CAPITAL", "500000"))
    )
    market_open: str = "09:15"
    market_close: str = "15:30"
    square_off_time: str = "15:15"
    index_symbol: str = "NIFTY 50"
    lot_size: int = 50           # NIFTY lot size
    instrument_exchange: str = "NFO"
    data_interval: str = "minute"
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


@dataclass
class APIConfig:
    """FastAPI server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    secret_key: str = field(
        default_factory=lambda: os.getenv("API_SECRET_KEY", "change-me-in-production")
    )


@dataclass
class NotificationConfig:
    """Notification settings (Telegram / email)."""
    telegram_token: Optional[str] = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN")
    )
    telegram_chat_id: Optional[str] = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID")
    )
    email_from: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_FROM"))
    email_to: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_TO"))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_password: Optional[str] = field(default_factory=lambda: os.getenv("SMTP_PASSWORD"))


@dataclass
class AppConfig:
    """Master application configuration — singleton."""
    database: DatabaseConfig      = field(default_factory=DatabaseConfig)
    redis: RedisConfig             = field(default_factory=RedisConfig)
    zerodha: ZerodhaConfig         = field(default_factory=ZerodhaConfig)
    angelone: AngelOneConfig       = field(default_factory=AngelOneConfig)
    fyers: FyersConfig             = field(default_factory=FyersConfig)
    upstox: UpstoxConfig           = field(default_factory=UpstoxConfig)
    risk: RiskConfig               = field(default_factory=RiskConfig)
    trading: TradingConfig         = field(default_factory=TradingConfig)
    api: APIConfig                 = field(default_factory=APIConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


# Singleton config instance — import this everywhere
config = AppConfig()

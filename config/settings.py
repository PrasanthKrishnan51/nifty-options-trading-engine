"""Global configuration — loaded from environment variables."""
import os
from dataclasses import dataclass, field
from typing import Optional
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./trading.db"))
    pool_size: int = 10; max_overflow: int = 20; echo: bool = False

@dataclass
class RedisConfig:
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = 0
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    ttl: int = 300

@dataclass
class ZerodhaConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ZERODHA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("ZERODHA_API_SECRET", ""))
    access_token: Optional[str] = field(default_factory=lambda: os.getenv("ZERODHA_ACCESS_TOKEN"))
    request_token: Optional[str] = field(default_factory=lambda: os.getenv("ZERODHA_REQUEST_TOKEN"))

@dataclass
class AngelOneConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ANGELONE_API_KEY", ""))
    client_id: str = field(default_factory=lambda: os.getenv("ANGELONE_CLIENT_ID", ""))
    password: str = field(default_factory=lambda: os.getenv("ANGELONE_PASSWORD", ""))
    totp_secret: Optional[str] = field(default_factory=lambda: os.getenv("ANGELONE_TOTP_SECRET"))
    access_token: Optional[str] = field(default_factory=lambda: os.getenv("ANGELONE_ACCESS_TOKEN"))

@dataclass
class FyersConfig:
    app_id: str = field(default_factory=lambda: os.getenv("FYERS_APP_ID", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("FYERS_SECRET_KEY", ""))
    redirect_uri: str = field(default_factory=lambda: os.getenv("FYERS_REDIRECT_URI", "https://127.0.0.1/"))
    access_token: Optional[str] = field(default_factory=lambda: os.getenv("FYERS_ACCESS_TOKEN"))

@dataclass
class UpstoxConfig:
    api_key: str = field(default_factory=lambda: os.getenv("UPSTOX_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("UPSTOX_API_SECRET", ""))
    redirect_uri: str = field(default_factory=lambda: os.getenv("UPSTOX_REDIRECT_URI", "https://127.0.0.1/"))
    access_token: Optional[str] = field(default_factory=lambda: os.getenv("UPSTOX_ACCESS_TOKEN"))
    rtoken: Optional[str] = field(default_factory=lambda: os.getenv("UPSTOX_RTOKEN"))

@dataclass
class RiskConfig:
    max_daily_loss_pct: float = 2.0
    max_position_size_pct: float = 5.0
    max_open_positions: int = 5
    default_stop_loss_pct: float = 30.0
    default_target_pct: float = 50.0
    trailing_stop_activation_pct: float = 20.0
    trailing_stop_pct: float = 10.0
    max_slippage_pct: float = 0.5

@dataclass
class TradingConfig:
    broker: str = field(default_factory=lambda: os.getenv("BROKER", "upstox"))
    paper_trading: bool = field(default_factory=lambda: os.getenv("PAPER_TRADING", "true").lower() == "true")
    capital: float = field(default_factory=lambda: float(os.getenv("TRADING_CAPITAL", "500000")))
    market_open: str = "09:15"; market_close: str = "15:30"; square_off_time: str = "15:15"
    index_symbol: str = "NIFTY 50"; lot_size: int = 50
    instrument_exchange: str = "NFO"; data_interval: str = "minute"
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

@dataclass
class APIConfig:
    host: str = "0.0.0.0"; port: int = 8000; debug: bool = False
    secret_key: str = field(default_factory=lambda: os.getenv("API_SECRET_KEY", "change-me-in-production"))

@dataclass
class NotificationConfig:
    telegram_token: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: Optional[str] = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    email_from: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_FROM"))
    email_to: Optional[str] = field(default_factory=lambda: os.getenv("EMAIL_TO"))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_password: Optional[str] = field(default_factory=lambda: os.getenv("SMTP_PASSWORD"))

@dataclass
class AppConfig:
    database:      DatabaseConfig      = field(default_factory=DatabaseConfig)
    redis:         RedisConfig         = field(default_factory=RedisConfig)
    zerodha:       ZerodhaConfig       = field(default_factory=ZerodhaConfig)
    angelone:      AngelOneConfig      = field(default_factory=AngelOneConfig)
    fyers:         FyersConfig         = field(default_factory=FyersConfig)
    upstox:        UpstoxConfig        = field(default_factory=UpstoxConfig)
    risk:          RiskConfig          = field(default_factory=RiskConfig)
    trading:       TradingConfig       = field(default_factory=TradingConfig)
    api:           APIConfig           = field(default_factory=APIConfig)
    notifications: NotificationConfig  = field(default_factory=NotificationConfig)

config = AppConfig()

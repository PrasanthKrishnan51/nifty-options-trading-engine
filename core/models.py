"""
Core domain models for the Options Trading System.
Defines all fundamental data structures used across the application.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OptionType(str, Enum):
    """CE = Call Option, PE = Put Option."""
    CE = "CE"
    PE = "PE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


class SignalType(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    EXIT = "EXIT"
    NO_SIGNAL = "NO_SIGNAL"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class BrokerType(str, Enum):
    ZERODHA = "zerodha"
    UPSTOX = "upstox"


class StrategyType(str, Enum):
    BREAKOUT = "breakout"
    MA_CROSSOVER = "ma_crossover"
    VWAP = "vwap"
    MOMENTUM = "momentum"


# ─────────────────────────────────────────────
#  Market Data Models
# ─────────────────────────────────────────────

@dataclass
class OHLCV:
    """Single candlestick / bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str = ""

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3

    def __repr__(self) -> str:
        return (
            f"OHLCV({self.symbol} {self.timestamp:%Y-%m-%d %H:%M} "
            f"O={self.open} H={self.high} L={self.low} C={self.close} V={self.volume})"
        )


@dataclass
class Tick:
    """Real-time market tick."""
    symbol: str
    ltp: float                       # Last traded price
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: int = 0                      # Open interest
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OptionChainEntry:
    """Single strike in an options chain."""
    strike: float
    expiry: datetime
    option_type: OptionType
    symbol: str
    ltp: float
    bid: float
    ask: float
    iv: float                        # Implied volatility
    delta: float
    theta: float
    vega: float
    gamma: float
    oi: int
    volume: int


# ─────────────────────────────────────────────
#  Signal & Order Models
# ─────────────────────────────────────────────

@dataclass
class Signal:
    """Trading signal produced by a strategy."""
    signal_type: SignalType
    strategy_name: str
    symbol: str
    option_type: Optional[OptionType]
    strike: Optional[float]
    expiry: Optional[datetime]
    confidence: float                # 0.0 – 1.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Order:
    """Represents a trading order."""
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float = 0.0
    trigger_price: float = 0.0
    product: str = "MIS"             # MIS = intraday
    validity: str = "DAY"
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_price: float = 0.0
    tag: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None


@dataclass
class Position:
    """Open or closed trading position."""
    position_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    exchange: str = "NFO"
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None
    expiry: Optional[datetime] = None
    entry_order: Optional[Order] = None
    exit_order: Optional[Order] = None
    quantity: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    trailing_sl: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    strategy_name: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None

    def update_pnl(self, ltp: float) -> None:
        """Recalculate unrealised P&L at current price."""
        self.pnl = (ltp - self.entry_price) * self.quantity
        self.pnl_pct = ((ltp - self.entry_price) / self.entry_price) * 100


# ─────────────────────────────────────────────
#  Performance / Backtest Models
# ─────────────────────────────────────────────

@dataclass
class Trade:
    """A completed round-trip trade (backtest or live)."""
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    strategy_name: str = ""
    option_type: Optional[OptionType] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    exit_reason: str = ""            # "TARGET", "SL", "TRAILING_SL", "EOD"


@dataclass
class PerformanceMetrics:
    """Summary statistics for a strategy run."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    expectancy: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_holding_period_minutes: float = 0.0

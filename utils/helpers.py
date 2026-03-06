"""Utility helpers: IST timezone, market hours, strike rounding, formatting."""
from __future__ import annotations
from datetime import datetime, time, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
    def now_ist() -> datetime:
        return datetime.now(IST)
except ImportError:
    IST = None  # type: ignore
    def now_ist() -> datetime:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)

MARKET_OPEN  = time(9, 15)
MARKET_CLOSE = time(15, 30)
SQUARE_OFF   = time(15, 15)


def is_market_open(dt: datetime | None = None) -> bool:
    dt = dt or now_ist()
    t = dt.time() if hasattr(dt, 'time') else MARKET_OPEN
    return dt.weekday() < 5 and MARKET_OPEN <= t <= MARKET_CLOSE

def is_square_off_time(dt: datetime | None = None) -> bool:
    dt = dt or now_ist()
    return dt.time() >= SQUARE_OFF

def round_to_strike(price: float, step: int = 50) -> float:
    return round(price / step) * step

def next_thursday(from_date: datetime | None = None) -> datetime:
    from_date = from_date or now_ist()
    days = (3 - from_date.weekday()) % 7
    if days == 0 and from_date.time() >= MARKET_CLOSE:
        days = 7
    return (from_date + timedelta(days=days)).replace(hour=15, minute=30, second=0, microsecond=0)

def format_inr(amount: float) -> str:
    return f"₹{amount:,.2f}"

def pct_change(old: float, new: float) -> float:
    return (new - old) / old * 100 if old != 0 else 0.0

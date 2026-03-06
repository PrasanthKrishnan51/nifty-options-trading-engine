"""
Market data utilities — synthetic data generator + live feed wrapper.
Used mainly for testing and demo mode.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime


def get_mock_data(n: int = 200, symbol: str = "NIFTY", seed: int = 42) -> pd.DataFrame:
    """Generate realistic synthetic NIFTY OHLCV data."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-15 09:15", periods=n, freq="1min")
    close = 21500 + np.cumsum(np.random.normal(0.3, 12, n))
    df = pd.DataFrame({
        "open":   close - np.abs(np.random.normal(5, 3, n)),
        "high":   close + np.abs(np.random.normal(15, 5, n)),
        "low":    close - np.abs(np.random.normal(15, 5, n)),
        "close":  close,
        "volume": np.random.randint(50_000, 300_000, n),
    }, index=dates)
    df.attrs["symbol"] = symbol
    return df


def get_live_data(broker, symbol: str = "NIFTY", exchange: str = "NSE",
                  interval: str = "minute", days: int = 1) -> pd.DataFrame:
    """Fetch live OHLCV data from the connected broker."""
    from datetime import timedelta
    to_date   = datetime.now()
    from_date = to_date - timedelta(days=days)
    return broker.get_historical_data(symbol, exchange, interval, from_date, to_date)

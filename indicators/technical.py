"""
Technical Indicators — pure pandas/numpy, no external TA lib required.

Available: ema, sma, rsi, macd, atr, bollinger_bands, vwap, supertrend,
           stochastic, adx, pivot_points, add_all_indicators
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]; low = df["low"]; close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()

def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    middle = sma(series, period)
    std = series.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return pd.DataFrame({"bb_upper": upper, "bb_middle": middle, "bb_lower": lower,
                         "bb_width": (upper - lower) / middle.replace(0, np.nan),
                         "bb_pct": (series - lower) / (upper - lower).replace(0, np.nan)})

def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical * df["volume"]
    if isinstance(df.index, pd.DatetimeIndex):
        date_groups = df.index.date
        cumtp, cumvol = pd.Series(dtype=float, index=df.index), pd.Series(dtype=float, index=df.index)
        for d in np.unique(date_groups):
            mask = date_groups == d
            cumtp[mask] = tp_vol[mask].cumsum().values
            cumvol[mask] = df["volume"][mask].cumsum().values
    else:
        cumtp = tp_vol.cumsum(); cumvol = df["volume"].cumsum()
    return cumtp / cumvol.replace(0, np.nan)

def supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> pd.DataFrame:
    atr_val = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    basic_upper = hl2 + multiplier * atr_val
    basic_lower = hl2 - multiplier * atr_val
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    for i in range(1, len(df)):
        pu, pl, pc = final_upper.iloc[i-1], final_lower.iloc[i-1], df["close"].iloc[i-1]
        final_upper.iloc[i] = basic_upper.iloc[i] if basic_upper.iloc[i] < pu or pc > pu else pu
        final_lower.iloc[i] = basic_lower.iloc[i] if basic_lower.iloc[i] > pl or pc < pl else pl
    supertrend_val = pd.Series(np.nan, index=df.index)
    trend = pd.Series(1, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > final_upper.iloc[i-1]: trend.iloc[i] = 1
        elif df["close"].iloc[i] < final_lower.iloc[i-1]: trend.iloc[i] = -1
        else: trend.iloc[i] = trend.iloc[i-1]
        supertrend_val.iloc[i] = final_lower.iloc[i] if trend.iloc[i] == 1 else final_upper.iloc[i]
    return pd.DataFrame({"supertrend": supertrend_val, "trend": trend})

def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df["high"]; low = df["low"]
    plus_dm = high.diff(); minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr_val = atr(df, period)
    plus_di = 100 * ema(plus_dm, period) / atr_val.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, period) / atr_val.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": ema(dx, period), "plus_di": plus_di, "minus_di": minus_di})

def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    stoch_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    return pd.DataFrame({"stoch_k": stoch_k, "stoch_d": stoch_k.rolling(d_period).mean()})

def pivot_points(high: float, low: float, close: float) -> dict:
    pivot = (high + low + close) / 3
    return dict(pivot=pivot, r1=2*pivot-low, r2=pivot+(high-low), r3=high+2*(pivot-low),
                s1=2*pivot-high, s2=pivot-(high-low), s3=low-2*(high-pivot))

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema9"] = ema(df["close"], 9); df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50); df["sma200"] = sma(df["close"], 200)
    df["rsi14"] = rsi(df["close"], 14); df["atr14"] = atr(df, 14)
    if "volume" in df.columns: df["vwap"] = vwap(df)
    macd_df = macd(df["close"])
    df["macd"] = macd_df["macd"]; df["macd_sig"] = macd_df["signal"]; df["macd_hist"] = macd_df["histogram"]
    bb = bollinger_bands(df["close"])
    df["bb_upper"] = bb["bb_upper"]; df["bb_middle"] = bb["bb_middle"]; df["bb_lower"] = bb["bb_lower"]
    st = supertrend(df); df["supertrend"] = st["supertrend"]; df["st_trend"] = st["trend"]
    adx_df = adx(df); df["adx"] = adx_df["adx"]; df["plus_di"] = adx_df["plus_di"]; df["minus_di"] = adx_df["minus_di"]
    return df

"""
Additional Trading Strategies: MA Crossover, VWAP, Momentum.
All extend BaseStrategy and produce BUY_CE / BUY_PE / NO_SIGNAL.
"""
from __future__ import annotations
import logging
from datetime import time
import pandas as pd
from core.models import OptionType, Signal, SignalType, StrategyType
from indicators.technical import ema, rsi as calc_rsi, macd as calc_macd, vwap as calc_vwap
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class MACrossoverStrategy(BaseStrategy):
    """EMA(fast) × EMA(slow) crossover with RSI filter."""

    def __init__(self, fast_period: int = 9, slow_period: int = 21, rsi_period: int = 14) -> None:
        super().__init__("MACrossoverStrategy", StrategyType.MA_CROSSOVER)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.parameters = {"fast": fast_period, "slow": slow_period, "rsi": rsi_period}

    def pre_process(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = ema(df["close"], self.fast_period)
        df["ema_slow"] = ema(df["close"], self.slow_period)
        df["rsi"]      = calc_rsi(df["close"], self.rsi_period)
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        if not self.validate_data(df, min_rows=self.slow_period + 5):
            return self.no_signal(symbol)
        if "ema_fast" not in df.columns:
            df = self.pre_process(df)

        prev = df.iloc[-2]; curr = df.iloc[-1]
        fast_cross_up   = prev["ema_fast"] <= prev["ema_slow"] and curr["ema_fast"] > curr["ema_slow"]
        fast_cross_down = prev["ema_fast"] >= prev["ema_slow"] and curr["ema_fast"] < curr["ema_slow"]
        current_rsi = curr.get("rsi", 50)

        if fast_cross_up and current_rsi > 55:
            return self._make_signal(df, symbol, SignalType.BUY_CE, OptionType.CE, current_rsi)
        if fast_cross_down and current_rsi < 45:
            return self._make_signal(df, symbol, SignalType.BUY_PE, OptionType.PE, current_rsi)
        return self.no_signal(symbol)

    def _make_signal(self, df, symbol, stype, otype, current_rsi):
        close = df.iloc[-1]["close"]
        conf  = min(0.85, 0.5 + abs(current_rsi - 50) / 100)
        return Signal(signal_type=stype, strategy_name=self.name, symbol=symbol,
                      option_type=otype, strike=None, expiry=None,
                      confidence=round(conf, 2), entry_price=close,
                      metadata={"rsi": round(current_rsi, 2)})


class VWAPStrategy(BaseStrategy):
    """Price deviation from VWAP — mean-reversion / trend following."""

    def __init__(self, deviation_threshold_pct: float = 0.3, rsi_period: int = 14) -> None:
        super().__init__("VWAPStrategy", StrategyType.VWAP)
        self.deviation_threshold_pct = deviation_threshold_pct
        self.rsi_period = rsi_period
        self.parameters = {"deviation_pct": deviation_threshold_pct}

    def pre_process(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "volume" in df.columns:
            df["vwap"] = calc_vwap(df)
        else:
            df["vwap"] = df["close"].rolling(20).mean()
        df["rsi"] = calc_rsi(df["close"], self.rsi_period)
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        if not self.validate_data(df, min_rows=30):
            return self.no_signal(symbol)
        if "vwap" not in df.columns:
            df = self.pre_process(df)

        curr = df.iloc[-1]
        close, vwap_val = curr["close"], curr.get("vwap", curr["close"])
        current_rsi = curr.get("rsi", 50)
        if vwap_val == 0:
            return self.no_signal(symbol)

        deviation = (close - vwap_val) / vwap_val * 100

        if deviation > self.deviation_threshold_pct and current_rsi > 55:
            conf = min(0.8, 0.4 + abs(deviation) / 2)
            return Signal(signal_type=SignalType.BUY_CE, strategy_name=self.name, symbol=symbol,
                          option_type=OptionType.CE, strike=None, expiry=None,
                          confidence=round(conf, 2), entry_price=close,
                          metadata={"vwap": round(vwap_val, 2), "deviation_pct": round(deviation, 2)})

        if deviation < -self.deviation_threshold_pct and current_rsi < 45:
            conf = min(0.8, 0.4 + abs(deviation) / 2)
            return Signal(signal_type=SignalType.BUY_PE, strategy_name=self.name, symbol=symbol,
                          option_type=OptionType.PE, strike=None, expiry=None,
                          confidence=round(conf, 2), entry_price=close,
                          metadata={"vwap": round(vwap_val, 2), "deviation_pct": round(deviation, 2)})

        return self.no_signal(symbol)


class MomentumStrategy(BaseStrategy):
    """MACD histogram sign-change with EMA trend + RSI confirmation."""

    def __init__(self, macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
                 ema_trend: int = 50, rsi_period: int = 14) -> None:
        super().__init__("MomentumStrategy", StrategyType.MOMENTUM)
        self.macd_fast   = macd_fast
        self.macd_slow   = macd_slow
        self.macd_signal = macd_signal
        self.ema_trend   = ema_trend
        self.rsi_period  = rsi_period
        self.parameters  = {"macd_fast": macd_fast, "macd_slow": macd_slow}

    def pre_process(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        macd_df = calc_macd(df["close"], self.macd_fast, self.macd_slow, self.macd_signal)
        df["macd"]      = macd_df["macd"]
        df["macd_sig"]  = macd_df["signal"]
        df["macd_hist"] = macd_df["histogram"]
        df["ema_trend"] = ema(df["close"], self.ema_trend)
        df["rsi"]       = calc_rsi(df["close"], self.rsi_period)
        return df

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        if not self.validate_data(df, min_rows=self.macd_slow + 10):
            return self.no_signal(symbol)
        if "macd_hist" not in df.columns:
            df = self.pre_process(df)

        prev = df.iloc[-2]; curr = df.iloc[-1]
        hist_turns_positive = prev["macd_hist"] < 0 < curr["macd_hist"]
        hist_turns_negative = prev["macd_hist"] > 0 > curr["macd_hist"]
        close = curr["close"]
        trend_ema  = curr.get("ema_trend", close)
        current_rsi = curr.get("rsi", 50)

        if hist_turns_positive and close > trend_ema and current_rsi < 70:
            conf = min(0.82, 0.5 + curr["macd_hist"] * 0.01)
            return Signal(signal_type=SignalType.BUY_CE, strategy_name=self.name, symbol=symbol,
                          option_type=OptionType.CE, strike=None, expiry=None,
                          confidence=round(conf, 2), entry_price=close,
                          metadata={"macd_hist": round(float(curr["macd_hist"]), 4), "rsi": round(current_rsi, 2)})

        if hist_turns_negative and close < trend_ema and current_rsi > 30:
            conf = min(0.82, 0.5 + abs(curr["macd_hist"]) * 0.01)
            return Signal(signal_type=SignalType.BUY_PE, strategy_name=self.name, symbol=symbol,
                          option_type=OptionType.PE, strike=None, expiry=None,
                          confidence=round(conf, 2), entry_price=close,
                          metadata={"macd_hist": round(float(curr["macd_hist"]), 4), "rsi": round(current_rsi, 2)})

        return self.no_signal(symbol)

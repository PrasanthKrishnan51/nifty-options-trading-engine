"""
Breakout Strategy for Options Buying.

Logic:
- Calculates the Opening Range (first N minutes after market open).
- Generates BUY CE signal when price breaks above the range high.
- Generates BUY PE signal when price breaks below the range low.
- Uses ATR for SL/Target calculation.
- RSI filter to confirm momentum direction.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Optional

import pandas as pd

from core.models import OptionType, Signal, SignalType, StrategyType
from indicators.technical import atr, rsi
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """
    Opening Range Breakout (ORB) strategy for option buying.

    Parameters
    ----------
    orb_minutes : int
        Number of minutes to define the opening range (default 15).
    atr_period : int
        Period for ATR calculation.
    rsi_period : int
        Period for RSI filter.
    rsi_overbought : float
        RSI level above which CE buys are avoided (default 75).
    rsi_oversold : float
        RSI level below which PE buys are avoided (default 25).
    sl_atr_multiplier : float
        Stop loss = entry_price - (ATR * multiplier).
    target_atr_multiplier : float
        Target = entry_price + (ATR * multiplier).
    """

    def __init__(
        self,
        orb_minutes: int = 15,
        atr_period: int = 14,
        rsi_period: int = 14,
        rsi_overbought: float = 75.0,
        rsi_oversold: float = 25.0,
        sl_atr_multiplier: float = 1.5,
        target_atr_multiplier: float = 3.0,
    ) -> None:
        super().__init__(name="BreakoutStrategy", strategy_type=StrategyType.BREAKOUT)
        self.orb_minutes = orb_minutes
        self.atr_period = atr_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.sl_atr_multiplier = sl_atr_multiplier
        self.target_atr_multiplier = target_atr_multiplier
        self.parameters = {
            "orb_minutes": orb_minutes,
            "atr_period": atr_period,
            "rsi_period": rsi_period,
        }

        # State
        self._orb_high: Optional[float] = None
        self._orb_low: Optional[float] = None
        self._signal_fired_today: bool = False
        self._last_reset_date: Optional[datetime] = None

    def pre_process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ATR and RSI columns to the dataframe."""
        df = df.copy()
        df["atr"] = atr(df, self.atr_period)
        df["rsi"] = rsi(df["close"], self.rsi_period)
        return df

    def _reset_daily_state(self, today: datetime) -> None:
        date = today.date()
        if self._last_reset_date != date:
            self._orb_high = None
            self._orb_low = None
            self._signal_fired_today = False
            self._last_reset_date = date
            logger.debug("BreakoutStrategy: daily state reset for %s", date)

    def _calculate_orb(self, df: pd.DataFrame) -> None:
        """
        Calculate Opening Range from the first `orb_minutes` candles of the session.
        Assumes df.index is a DatetimeIndex.
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            return

        today = df.index[-1].date()
        market_open = pd.Timestamp(f"{today} 09:15:00", tz=df.index.tz)
        orb_end = pd.Timestamp(f"{today} 09:15:00", tz=df.index.tz) + pd.Timedelta(
            minutes=self.orb_minutes
        )

        orb_candles = df[(df.index >= market_open) & (df.index <= orb_end)]
        if orb_candles.empty:
            return

        self._orb_high = orb_candles["high"].max()
        self._orb_low = orb_candles["low"].min()
        logger.info(
            "ORB calculated: HIGH=%.2f LOW=%.2f (from %d candles)",
            self._orb_high, self._orb_low, len(orb_candles)
        )

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        """
        Generate a breakout signal.

        Returns BUY_CE if price breaks above ORB high with RSI confirming,
        BUY_PE if price breaks below ORB low with RSI confirming,
        otherwise NO_SIGNAL.
        """
        if not self.validate_data(df, min_rows=self.atr_period + 5):
            return self.no_signal(symbol)

        # Pre-process if columns not already present
        if "atr" not in df.columns:
            df = self.pre_process(df)

        latest = df.iloc[-1]
        current_time = df.index[-1]

        # Reset state at start of each day
        self._reset_daily_state(current_time)

        # Calculate ORB if not yet done
        if self._orb_high is None:
            self._calculate_orb(df)

        if self._orb_high is None or self._orb_low is None:
            return self.no_signal(symbol)

        # Only trade between 09:30 and 14:30
        trade_start = time(9, 30)
        trade_end = time(14, 30)
        if not (trade_start <= current_time.time() <= trade_end):
            return self.no_signal(symbol)

        # One signal per day
        if self._signal_fired_today:
            return self.no_signal(symbol)

        close = latest["close"]
        current_atr = latest.get("atr", (self._orb_high - self._orb_low))
        current_rsi = latest.get("rsi", 50.0)

        signal_type = SignalType.NO_SIGNAL
        option_type = None
        confidence = 0.0

        # ── Bullish Breakout → BUY CE ─────────────────────────────
        if close > self._orb_high and current_rsi < self.rsi_overbought:
            breakout_magnitude = (close - self._orb_high) / self._orb_high
            signal_type = SignalType.BUY_CE
            option_type = OptionType.CE
            confidence = min(0.9, 0.5 + breakout_magnitude * 10)

        # ── Bearish Breakdown → BUY PE ────────────────────────────
        elif close < self._orb_low and current_rsi > self.rsi_oversold:
            breakdown_magnitude = (self._orb_low - close) / self._orb_low
            signal_type = SignalType.BUY_PE
            option_type = OptionType.PE
            confidence = min(0.9, 0.5 + breakdown_magnitude * 10)

        if signal_type == SignalType.NO_SIGNAL:
            return self.no_signal(symbol)

        # Calculate SL / Target based on ATR
        stop_loss_distance = current_atr * self.sl_atr_multiplier
        target_distance = current_atr * self.target_atr_multiplier

        self._signal_fired_today = True

        signal = Signal(
            signal_type=signal_type,
            strategy_name=self.name,
            symbol=symbol,
            option_type=option_type,
            strike=None,          # Strike selection handled by execution engine
            expiry=None,          # Expiry selection handled by execution engine
            confidence=round(confidence, 2),
            entry_price=close,
            stop_loss=round(close - stop_loss_distance, 2),
            target=round(close + target_distance, 2),
            metadata={
                "orb_high": self._orb_high,
                "orb_low": self._orb_low,
                "atr": round(current_atr, 2),
                "rsi": round(current_rsi, 2),
            },
        )

        logger.info(
            "SIGNAL | %s | %s | entry=%.2f sl=%.2f target=%.2f conf=%.2f",
            self.name, signal_type.value, close,
            signal.stop_loss, signal.target, confidence,
        )
        return signal

"""Abstract BaseStrategy — all concrete strategies must subclass this."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
from core.models import Signal, SignalType, StrategyType, OptionType

class BaseStrategy(ABC):
    def __init__(self, name: str, strategy_type: StrategyType = StrategyType.BREAKOUT) -> None:
        self.name = name
        self.strategy_type = strategy_type
        self.enabled: bool = True
        self.parameters: dict = {}

    @abstractmethod
    def pre_process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicator columns to df. Must return a copy."""

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        """Analyse df and return a Signal (NO_SIGNAL if nothing actionable)."""

    def validate_data(self, df: pd.DataFrame, min_rows: int = 30) -> bool:
        if df is None or len(df) < min_rows:
            return False
        required = {"open", "high", "low", "close"}
        return required.issubset(df.columns)

    def no_signal(self, symbol: str) -> Signal:
        return Signal(
            signal_type=SignalType.NO_SIGNAL,
            strategy_name=self.name,
            symbol=symbol,
            option_type=None, strike=None, expiry=None,
            confidence=0.0,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(enabled={self.enabled})"

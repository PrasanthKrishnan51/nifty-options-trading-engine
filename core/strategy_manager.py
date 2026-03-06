"""
Strategy Manager — registers, enables/disables and dispatches signals.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional
import pandas as pd
from core.models import Signal, SignalType
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyManager:
    def __init__(self) -> None:
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.name] = strategy
        logger.info("Strategy registered: %s", strategy.name)

    def unregister(self, name: str) -> None:
        self._strategies.pop(name, None)

    def enable(self, name: str) -> bool:
        if name in self._strategies:
            self._strategies[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self._strategies:
            self._strategies[name].enabled = False
            return True
        return False

    def get_all_signals(self, df: pd.DataFrame, symbol: str) -> List[Signal]:
        signals: List[Signal] = []
        for strategy in self._strategies.values():
            if not strategy.enabled:
                continue
            try:
                processed = strategy.pre_process(df)
                signal = strategy.generate_signal(processed, symbol)
                if signal.signal_type != SignalType.NO_SIGNAL:
                    signals.append(signal)
                    logger.info("Signal from %s: %s (conf=%.2f)",
                                strategy.name, signal.signal_type.value, signal.confidence)
            except Exception as exc:
                logger.exception("Strategy %s raised: %s", strategy.name, exc)
        return signals

    def get_best_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        signals = self.get_all_signals(df, symbol)
        if not signals:
            return None
        return max(signals, key=lambda s: s.confidence)

    @property
    def strategies(self) -> Dict[str, BaseStrategy]:
        return self._strategies

    def info(self) -> List[dict]:
        return [{"name": s.name, "type": s.strategy_type.value, "enabled": s.enabled,
                 "parameters": s.parameters} for s in self._strategies.values()]

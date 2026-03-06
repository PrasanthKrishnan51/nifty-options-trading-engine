"""
DataFeed — coordinates historical and live market data from any broker.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Callable, List, Optional
import pandas as pd
from broker.base_broker import BaseBroker
from core.models import Tick

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self, broker: BaseBroker) -> None:
        self._broker = broker

    def get_ohlcv(self, symbol: str, exchange: str = "NSE",
                  interval: str = "minute", days: int = 1) -> pd.DataFrame:
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=days)
        df = self._broker.get_historical_data(symbol, exchange, interval, from_date, to_date)
        if df.empty:
            logger.warning("DataFeed: no data for %s/%s", symbol, interval)
        return df

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Optional[float]:
        return self._broker.get_ltp(symbol, exchange)

    def subscribe_live(self, symbols: List[str],
                       callback: Callable[[Tick], None]) -> None:
        self._broker.subscribe(symbols, callback)

    def unsubscribe_live(self, symbols: List[str]) -> None:
        self._broker.unsubscribe(symbols)

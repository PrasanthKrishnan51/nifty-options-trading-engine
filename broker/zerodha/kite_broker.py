"""ZerodhaBroker — stub adapter. Fill in with the broker's SDK calls."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
from broker.base_broker import BaseBroker
from core.models import Order, OrderStatus, Position, Tick

logger = logging.getLogger(__name__)

class ZerodhaBroker(BaseBroker):
    def __init__(self):
        super().__init__("zerodha")
    def connect(self) -> bool:
        logger.warning("ZerodhaBroker.connect() not implemented"); return False
    def disconnect(self) -> None: self._connected = False
    def get_quote(self, symbol, exchange="NSE"): return None
    def get_ltp(self, symbol, exchange="NSE"): return None
    def get_historical_data(self, symbol, exchange, interval, from_date, to_date): return pd.DataFrame()
    def get_option_chain(self, underlying, expiry): return []
    def place_order(self, order):
        order.status = OrderStatus.REJECTED; order.error_message = "Not implemented"; return order
    def modify_order(self, order): return order
    def cancel_order(self, order_id): return False
    def get_order_status(self, order_id): return OrderStatus.PENDING
    def get_orders(self): return []
    def get_positions(self): return []
    def get_portfolio(self): return {}
    def get_funds(self): return {"available": 0.0, "used": 0.0, "total": 0.0}
    def subscribe(self, symbols, callback): pass
    def unsubscribe(self, symbols): pass

"""
OrderManager — thin wrapper kept for backwards compatibility.
The full implementation lives in execution/execution_engine.py.
"""
from __future__ import annotations
import logging
from core.models import Order, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, broker) -> None:
        self.broker = broker

    def execute(self, signal: str, symbol: str, qty: int) -> Order:
        side = OrderSide.BUY if signal in ("BUY_CALL", "BUY_CE", "BUY_PE", "BUY_PUT") else OrderSide.SELL
        order = Order(symbol=symbol, exchange="NFO", side=side,
                      order_type=OrderType.MARKET, quantity=qty)
        placed = self.broker.place_order(order)
        logger.info("OrderManager.execute: %s %s qty=%d → %s",
                    side.value, symbol, qty, placed.status.value)
        return placed

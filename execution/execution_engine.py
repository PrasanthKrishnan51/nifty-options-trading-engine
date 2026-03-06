"""
Execution Engine — order placement, retry logic, strike selection, paper trading.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Optional

from broker.base_broker import BaseBroker
from config.settings import config
from core.models import (
    Order, OrderSide, OrderStatus, OrderType,
    Position, PositionStatus, Signal, SignalType,
)
from options.option_selector import OptionSelector
from risk_management.risk_manager import RiskManager

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2   # seconds


class ExecutionEngine:
    """
    Bridges signals → orders → positions.

    In paper trading mode, orders are simulated without real API calls.
    """

    def __init__(self, broker: BaseBroker, risk_manager: RiskManager) -> None:
        self._broker       = broker
        self._risk         = risk_manager
        self._paper        = config.trading.paper_trading
        self._lot_size     = config.trading.lot_size
        self._selector     = OptionSelector(otm_offset=0, min_oi=50_000)

    # ── Public API ────────────────────────────────────────────────

    def process_signal(self, signal: Signal, capital: float) -> Optional[Position]:
        """
        Convert a signal into a live/paper position.

        Returns the opened Position or None on failure.
        """
        if signal.signal_type == SignalType.NO_SIGNAL:
            return None

        # Pre-trade risk gate
        ok, reason = self._risk.can_trade(capital)
        if not ok:
            logger.warning("Signal blocked by risk: %s", reason)
            return None

        if not self._risk.validate_signal_risk(signal):
            return None

        # Determine entry price
        if signal.entry_price:
            entry_price = signal.entry_price
        else:
            ltp = self._broker.get_ltp(signal.symbol)
            entry_price = ltp or 0.0

        if entry_price <= 0:
            logger.warning("Invalid entry price for %s", signal.symbol)
            return None

        # Position sizing
        sl    = signal.stop_loss or self._risk.compute_stop_loss(entry_price, entry_price)
        target= signal.target    or self._risk.compute_target(entry_price, entry_price)
        lots  = self._risk.calculate_position_size(
            capital, entry_price, sl, self._lot_size, signal.confidence
        )
        qty = lots * self._lot_size

        # Build order
        order = Order(
            symbol     = signal.symbol,
            exchange   = config.trading.instrument_exchange,
            side       = OrderSide.BUY,
            order_type = OrderType.MARKET,
            quantity   = qty,
            product    = "MIS",
            tag        = signal.strategy_name[:20],
        )

        # Place (with retry)
        placed = self._place_with_retry(order)
        if placed.status not in (OrderStatus.OPEN, OrderStatus.COMPLETE):
            logger.error("Order failed: %s — %s", placed.status, placed.error_message)
            return None

        avg_price = placed.avg_price if placed.avg_price > 0 else entry_price

        # Create position
        position = Position(
            symbol         = signal.symbol,
            exchange       = order.exchange,
            option_type    = signal.option_type,
            strike         = signal.strike,
            expiry         = signal.expiry,
            entry_order    = placed,
            quantity       = qty,
            entry_price    = avg_price,
            stop_loss      = sl,
            target         = target,
            strategy_name  = signal.strategy_name,
            status         = PositionStatus.OPEN,
        )

        self._risk.register_position(position)
        logger.info("Position opened: %s qty=%d entry=%.2f sl=%.2f target=%.2f",
                    signal.symbol, qty, avg_price, sl, target)
        return position

    def close_position(self, position: Position, reason: str = "MANUAL") -> bool:
        """Close an open position with a market sell order."""
        order = Order(
            symbol     = position.symbol,
            exchange   = position.exchange,
            side       = OrderSide.SELL,
            order_type = OrderType.MARKET,
            quantity   = position.quantity,
            product    = "MIS",
            tag        = f"EXIT_{reason}"[:20],
        )
        placed = self._place_with_retry(order)
        if placed.status not in (OrderStatus.OPEN, OrderStatus.COMPLETE):
            logger.error("Exit order failed: %s", placed.error_message)
            return False

        exit_price = placed.avg_price if placed.avg_price > 0 else position.entry_price
        self._risk.close_position(position, exit_price)
        logger.info("Position closed: %s exit=%.2f pnl=%.2f reason=%s",
                    position.symbol, exit_price, position.pnl, reason)
        return True

    # ── Internal ──────────────────────────────────────────────────

    def _place_with_retry(self, order: Order) -> Order:
        if self._paper:
            return self._simulate_order(order)

        for attempt in range(1, _MAX_RETRIES + 1):
            placed = self._broker.place_order(order)
            if placed.status in (OrderStatus.OPEN, OrderStatus.COMPLETE):
                return placed
            if placed.status == OrderStatus.REJECTED:
                logger.error("Order rejected (attempt %d): %s", attempt, placed.error_message)
                break
            logger.warning("Order attempt %d failed, retrying...", attempt)
            time.sleep(_RETRY_DELAY)
        return order

    @staticmethod
    def _simulate_order(order: Order) -> Order:
        """Paper-trade simulation — always fills at market."""
        order.status         = OrderStatus.COMPLETE
        order.filled_qty     = order.quantity
        order.avg_price      = order.price if order.price > 0 else 100.0
        order.broker_order_id = f"PAPER_{int(datetime.now().timestamp())}"
        logger.info("PAPER TRADE: %s %s %d @ %.2f",
                    order.side.value, order.symbol, order.quantity, order.avg_price)
        return order

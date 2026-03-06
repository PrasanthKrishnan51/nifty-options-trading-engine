"""
Risk Management Engine.

Responsibilities:
- Position sizing (fixed fractional, Kelly criterion)
- Stop loss, target, trailing stop management
- Daily loss limit enforcement
- Max open positions enforcement
- Slippage estimation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional

from config.settings import config
from core.models import Order, OrderSide, OrderType, Position, PositionStatus, Signal

logger = logging.getLogger(__name__)


@dataclass
class DailyStats:
    """Tracks intraday P&L and trade counts."""
    date: date = field(default_factory=date.today)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    trades_taken: int = 0
    max_loss_breached: bool = False

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


class RiskManager:
    """
    Central risk management component.

    Thread-safe methods for checking risk limits and computing
    position sizes before any order is placed.
    """

    def __init__(self) -> None:
        self._cfg = config.risk
        self._trading_cfg = config.trading
        self._daily_stats: DailyStats = DailyStats()
        self._open_positions: Dict[str, Position] = {}  # position_id → Position

    # ── Daily Reset ───────────────────────────────────────────────

    def _ensure_daily_reset(self) -> None:
        """Reset daily statistics at the start of each trading day."""
        today = date.today()
        if self._daily_stats.date != today:
            logger.info("Risk manager: resetting daily stats for %s", today)
            self._daily_stats = DailyStats(date=today)

    # ── Pre-Trade Checks ──────────────────────────────────────────

    def can_trade(self, capital: float) -> tuple[bool, str]:
        """
        Master pre-trade gate.

        Returns
        -------
        (True, "") if trading is allowed.
        (False, reason) otherwise.
        """
        self._ensure_daily_reset()

        # Max daily loss
        max_loss_amount = capital * self._cfg.max_daily_loss_pct / 100
        if self._daily_stats.total_pnl <= -max_loss_amount:
            self._daily_stats.max_loss_breached = True
            return False, (
                f"Max daily loss reached: {self._daily_stats.total_pnl:.2f} "
                f"(limit: -{max_loss_amount:.2f})"
            )

        # Max open positions
        open_count = sum(
            1 for p in self._open_positions.values()
            if p.status == PositionStatus.OPEN
        )
        if open_count >= self._cfg.max_open_positions:
            return False, f"Max open positions reached: {open_count}"

        return True, ""

    def validate_signal_risk(self, signal: Signal) -> bool:
        """Validate that signal parameters meet minimum risk standards."""
        if signal.stop_loss and signal.entry_price:
            risk_pct = abs(signal.entry_price - signal.stop_loss) / signal.entry_price * 100
            if risk_pct > 50:   # Risk > 50% of entry is too wide for options
                logger.warning("Signal rejected: SL too wide (%.1f%%)", risk_pct)
                return False
        return True

    # ── Position Sizing ───────────────────────────────────────────

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss: float,
        lot_size: int = 50,
        confidence: float = 1.0,
    ) -> int:
        """
        Fixed-fractional position sizing with confidence scaling.

        Parameters
        ----------
        capital       : Total trading capital.
        entry_price   : Option premium (per unit).
        stop_loss     : Stop loss price.
        lot_size      : Lot size (e.g. NIFTY = 50).
        confidence    : Signal confidence [0, 1] to scale position.

        Returns
        -------
        int — number of lots to trade (minimum 1).
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 1

        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return 1

        max_risk_amount = capital * self._cfg.max_position_size_pct / 100
        max_risk_amount *= confidence                    # Scale by confidence

        raw_units = max_risk_amount / risk_per_unit
        raw_lots = int(raw_units / lot_size)

        lots = max(1, raw_lots)
        cost = lots * lot_size * entry_price

        # Cap so single position doesn't exceed max_position_size_pct of capital
        max_cost = capital * self._cfg.max_position_size_pct / 100
        if cost > max_cost:
            lots = max(1, int(max_cost / (lot_size * entry_price)))

        logger.debug(
            "Position size: %d lots | risk_per_unit=%.2f | max_risk=%.2f",
            lots, risk_per_unit, max_risk_amount
        )
        return lots

    # ── SL / Target Computation ───────────────────────────────────

    def compute_stop_loss(self, entry_price: float, option_premium: float) -> float:
        """Default SL: entry minus X% of option premium."""
        sl_amount = option_premium * self._cfg.default_stop_loss_pct / 100
        return round(entry_price - sl_amount, 2)

    def compute_target(self, entry_price: float, option_premium: float) -> float:
        """Default target: entry plus X% of option premium."""
        target_amount = option_premium * self._cfg.default_target_pct / 100
        return round(entry_price + target_amount, 2)

    def update_trailing_stop(self, position: Position, ltp: float) -> Optional[float]:
        """
        Recalculate trailing stop loss.

        Activates when profit >= trailing_stop_activation_pct.
        Then trails by trailing_stop_pct below the peak.

        Returns new trailing SL or None if not activated.
        """
        if position.entry_price <= 0:
            return None

        profit_pct = (ltp - position.entry_price) / position.entry_price * 100

        if profit_pct >= self._cfg.trailing_stop_activation_pct:
            new_trailing_sl = round(
                ltp * (1 - self._cfg.trailing_stop_pct / 100), 2
            )
            if new_trailing_sl > position.trailing_sl:
                position.trailing_sl = new_trailing_sl
                logger.debug(
                    "Trailing SL updated: %s → %.2f (ltp=%.2f, profit=%.1f%%)",
                    position.symbol, new_trailing_sl, ltp, profit_pct
                )
                return new_trailing_sl

        return None

    # ── Exit Checks ───────────────────────────────────────────────

    def should_exit(
        self, position: Position, ltp: float
    ) -> tuple[bool, str]:
        """
        Determine if a position should be exited.

        Returns (True, reason) or (False, "").
        """
        # Stop loss hit
        if position.stop_loss > 0 and ltp <= position.stop_loss:
            return True, "STOP_LOSS"

        # Target hit
        if position.target > 0 and ltp >= position.target:
            return True, "TARGET"

        # Trailing stop hit
        if position.trailing_sl > 0 and ltp <= position.trailing_sl:
            return True, "TRAILING_SL"

        return False, ""

    # ── P&L Tracking ─────────────────────────────────────────────

    def register_position(self, position: Position) -> None:
        """Register a newly opened position."""
        self._open_positions[position.position_id] = position
        self._daily_stats.trades_taken += 1
        logger.info("Position registered: %s | %s", position.symbol, position.position_id)

    def close_position(self, position: Position, exit_price: float) -> None:
        """Record P&L when a position is closed."""
        position.exit_price = exit_price
        position.pnl = (exit_price - position.entry_price) * position.quantity
        position.pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now()

        self._daily_stats.realized_pnl += position.pnl

        if position.position_id in self._open_positions:
            del self._open_positions[position.position_id]

        logger.info(
            "Position closed: %s | PnL=%.2f (%.1f%%)",
            position.symbol, position.pnl, position.pnl_pct
        )

    def update_unrealized_pnl(self, positions: List[Position], ltps: Dict[str, float]) -> None:
        """Refresh unrealised P&L for all open positions."""
        total_unrealized = 0.0
        for pos in positions:
            ltp = ltps.get(pos.symbol, pos.entry_price)
            pos.update_pnl(ltp)
            total_unrealized += pos.pnl
        self._daily_stats.unrealized_pnl = total_unrealized

    # ── Slippage ──────────────────────────────────────────────────

    def estimate_slippage(self, price: float) -> float:
        """Estimate slippage as a percentage of price (for backtesting)."""
        return price * self._cfg.max_slippage_pct / 100

    def apply_slippage(self, price: float, side: str = "BUY") -> float:
        """Apply slippage to a price (adverse for the trader)."""
        slippage = self.estimate_slippage(price)
        return price + slippage if side == "BUY" else price - slippage

    # ── Getters ───────────────────────────────────────────────────

    @property
    def daily_stats(self) -> DailyStats:
        self._ensure_daily_reset()
        return self._daily_stats

    @property
    def open_positions(self) -> Dict[str, Position]:
        return self._open_positions

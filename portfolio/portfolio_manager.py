"""
Portfolio Manager — tracks open positions, realized P&L, and performance.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Dict, List, Optional
from core.models import Position, PositionStatus, Trade

logger = logging.getLogger(__name__)


class PortfolioManager:
    def __init__(self, initial_capital: float = 500_000.0) -> None:
        self.initial_capital = initial_capital
        self.available_capital = initial_capital
        self._positions: Dict[str, Position] = {}
        self._closed_trades: List[Trade] = []
        self._realized_pnl: float = 0.0

    # ── Positions ─────────────────────────────────────────────────

    def add_position(self, position: Position) -> None:
        cost = position.entry_price * position.quantity
        if cost > self.available_capital:
            logger.warning("Insufficient capital for %s (need %.2f, have %.2f)",
                           position.symbol, cost, self.available_capital)
            return
        self._positions[position.position_id] = position
        self.available_capital -= cost
        logger.info("Position opened: %s @%.2f qty=%d",
                    position.symbol, position.entry_price, position.quantity)

    def close_position(self, position_id: str, exit_price: float,
                       exit_reason: str = "") -> Optional[Position]:
        pos = self._positions.pop(position_id, None)
        if not pos:
            logger.warning("close_position: id %s not found", position_id)
            return None

        pos.exit_price = exit_price
        pos.pnl = (exit_price - pos.entry_price) * pos.quantity
        pos.pnl_pct = (exit_price - pos.entry_price) / pos.entry_price * 100
        pos.status = PositionStatus.CLOSED
        pos.closed_at = datetime.now()

        self._realized_pnl += pos.pnl
        self.available_capital += pos.entry_price * pos.quantity + pos.pnl

        trade = Trade(symbol=pos.symbol, strategy_name=pos.strategy_name,
                      option_type=pos.option_type,
                      entry_price=pos.entry_price, exit_price=exit_price,
                      quantity=pos.quantity, pnl=pos.pnl, pnl_pct=pos.pnl_pct,
                      entry_time=pos.opened_at, exit_time=pos.closed_at,
                      exit_reason=exit_reason)
        self._closed_trades.append(trade)
        logger.info("Position closed: %s PnL=%.2f (%.1f%%)",
                    pos.symbol, pos.pnl, pos.pnl_pct)
        return pos

    def update_pnl(self, ltps: Dict[str, float]) -> None:
        for pos in self._positions.values():
            ltp = ltps.get(pos.symbol, pos.entry_price)
            pos.update_pnl(ltp)

    # ── Getters ───────────────────────────────────────────────────

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def closed_trades(self) -> List[Trade]:
        return self._closed_trades

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.pnl for p in self._positions.values())

    @property
    def total_pnl(self) -> float:
        return self._realized_pnl + self.unrealized_pnl

    @property
    def net_worth(self) -> float:
        return self.available_capital + sum(
            p.entry_price * p.quantity for p in self._positions.values()
        )

    def summary(self) -> dict:
        wins = [t for t in self._closed_trades if t.pnl > 0]
        return dict(
            initial_capital   = self.initial_capital,
            net_worth         = self.net_worth,
            available_capital = self.available_capital,
            realized_pnl      = self._realized_pnl,
            unrealized_pnl    = self.unrealized_pnl,
            open_positions    = len(self._positions),
            total_trades      = len(self._closed_trades),
            win_rate          = len(wins) / len(self._closed_trades) * 100 if self._closed_trades else 0,
        )

"""
LiveTrader — production live / paper trading loop.

Runs strategies on a configurable tick interval, manages positions,
enforces risk rules, and sends notifications on every event.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import List, Optional

from broker.factory import get_broker
from config.settings import config
from core.strategy_manager import StrategyManager
from data.data_feed import DataFeed
from execution.execution_engine import ExecutionEngine
from notifications.notifier import TradeNotifier
from portfolio.portfolio_manager import PortfolioManager
from risk_management.risk_manager import RiskManager
from strategies.base_strategy import BaseStrategy
from utils.helpers import is_market_open, is_square_off_time

logger = logging.getLogger(__name__)


class LiveTrader:
    """
    Main live trading orchestrator.

    Lifecycle:
        trader = LiveTrader(strategies=[BreakoutStrategy(), ...])
        trader.start()   # blocking loop
        trader.stop()    # graceful shutdown (call from another thread)
    """

    def __init__(self, strategies: List[BaseStrategy],
                 tick_interval: int = 60,
                 symbol: str = "NIFTY",
                 exchange: str = "NSE") -> None:
        self.symbol        = symbol
        self.exchange      = exchange
        self.tick_interval = tick_interval
        self._running      = False

        # Components
        self._broker    = get_broker()
        self._data_feed = DataFeed(self._broker)
        self._risk      = RiskManager()
        self._portfolio = PortfolioManager(config.trading.capital)
        self._execution = ExecutionEngine(self._broker, self._risk)
        self._notifier  = TradeNotifier()

        self._strategy_manager = StrategyManager()
        for s in strategies:
            self._strategy_manager.register(s)

    # ── Public ────────────────────────────────────────────────────

    def start(self) -> None:
        """Blocking trading loop. Stops at market close or on self.stop()."""
        logger.info("LiveTrader starting | broker=%s | paper=%s | strategies=%s",
                    self._broker.name, config.trading.paper_trading,
                    [s for s in self._strategy_manager.strategies])

        if not self._broker.connect():
            logger.error("Broker connection failed — aborting.")
            return

        self._running = True
        logger.info("LiveTrader running. Press Ctrl+C to stop.")

        try:
            while self._running:
                self._tick()
                time.sleep(self.tick_interval)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt — shutting down.")
        finally:
            self._shutdown()

    def stop(self) -> None:
        self._running = False

    # ── Tick ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = datetime.now()

        if not is_market_open():
            logger.debug("Market closed — skipping tick.")
            return

        # Square off at end of day
        if is_square_off_time():
            self._square_off_all("EOD")
            return

        # Check existing positions for exit conditions
        self._check_exits()

        # Fetch OHLCV and run strategies
        df = self._data_feed.get_ohlcv(self.symbol, self.exchange, interval="minute", days=1)
        if df.empty:
            logger.warning("Empty OHLCV data — skipping signal generation.")
            return

        signal = self._strategy_manager.get_best_signal(df, self.symbol)
        if signal is None:
            return

        capital = self._portfolio.available_capital
        position = self._execution.process_signal(signal, capital)

        if position:
            self._portfolio.add_position(position)
            self._notifier.on_trade_entry(
                symbol=position.symbol, entry_price=position.entry_price,
                stop_loss=position.stop_loss, target=position.target,
                quantity=position.quantity, strategy=position.strategy_name,
            )

    def _check_exits(self) -> None:
        positions = self._portfolio.open_positions
        if not positions:
            return

        for pos in list(positions):
            ltp = self._broker.get_ltp(pos.symbol) or pos.entry_price
            pos.update_pnl(ltp)

            # Update trailing stop
            self._risk.update_trailing_stop(pos, ltp)

            should_exit, reason = self._risk.should_exit(pos, ltp)
            if should_exit:
                success = self._execution.close_position(pos, reason)
                if success:
                    self._portfolio.close_position(pos.position_id, ltp, reason)
                    self._notifier.on_trade_exit(
                        symbol=pos.symbol, exit_price=ltp,
                        pnl=pos.pnl, pnl_pct=pos.pnl_pct,
                        reason=reason, strategy=pos.strategy_name,
                    )

    def _square_off_all(self, reason: str = "EOD") -> None:
        for pos in list(self._portfolio.open_positions):
            ltp = self._broker.get_ltp(pos.symbol) or pos.entry_price
            self._execution.close_position(pos, reason)
            self._portfolio.close_position(pos.position_id, ltp, reason)
        summary = self._portfolio.summary()
        self._notifier.on_daily_summary(
            realized_pnl=summary["realized_pnl"],
            trades=summary["total_trades"],
            win_rate=summary["win_rate"],
        )

    def _shutdown(self) -> None:
        logger.info("LiveTrader shutting down...")
        self._square_off_all("SHUTDOWN")
        self._broker.disconnect()

    # ── API-facing properties ─────────────────────────────────────

    @property
    def portfolio(self) -> PortfolioManager:
        return self._portfolio

    @property
    def risk(self) -> RiskManager:
        return self._risk

    @property
    def strategy_manager(self) -> StrategyManager:
        return self._strategy_manager

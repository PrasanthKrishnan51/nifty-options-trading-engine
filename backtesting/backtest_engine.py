"""
Backtesting Engine.

Simulates strategy execution on historical OHLCV data and
computes full performance metrics including Sharpe ratio,
drawdown, win rate, profit factor, and more.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Type

import numpy as np
import pandas as pd

from config.settings import config
from core.models import (
    OptionType, PerformanceMetrics, Signal, SignalType, Trade,
)
from risk_management.risk_manager import RiskManager
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.067   # Indian 10Y Gsec yield (annualised)
TRADING_DAYS_PER_YEAR = 252


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    initial_capital: float = 500_000.0
    lot_size: int = 50
    commission_per_lot: float = 40.0        # ₹ per lot (brokerage + taxes est.)
    sl_pct: float = 30.0                    # % of option premium as stop loss
    target_pct: float = 60.0               # % of option premium as target
    slippage_pct: float = 0.3              # % slippage on fills
    max_daily_loss_pct: float = 2.0
    square_off_time: str = "15:15"
    simulate_option_premium: bool = True   # Derive premium from ATR
    atr_premium_multiplier: float = 2.0    # premium ≈ ATR * multiplier


@dataclass
class BacktestResult:
    """Full result of a single backtest run."""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    config: BacktestConfig
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    daily_pnl: pd.Series = field(default_factory=pd.Series)


class BacktestEngine:
    """
    Event-driven backtester.

    Iterates over historical bars, calls strategy.generate_signal()
    on each bar, and simulates trade execution with realistic costs.
    """

    def __init__(self, bt_config: Optional[BacktestConfig] = None) -> None:
        self._cfg = bt_config or BacktestConfig(
            initial_capital=config.trading.capital
        )

    def run(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        symbol: str = "NIFTY",
    ) -> BacktestResult:
        """
        Execute a backtest.

        Parameters
        ----------
        strategy : BaseStrategy
        df       : pd.DataFrame — OHLCV historical data (datetime index).
        symbol   : str          — underlying symbol name.

        Returns
        -------
        BacktestResult
        """
        logger.info(
            "Backtest started | strategy=%s | symbol=%s | bars=%d",
            strategy.name, symbol, len(df)
        )
        df = strategy.pre_process(df)
        result = BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            start_date=df.index[0],
            end_date=df.index[-1],
            config=self._cfg,
        )

        capital = self._cfg.initial_capital
        equity = capital
        equity_series: List[tuple[datetime, float]] = []
        trades: List[Trade] = []

        current_trade: Optional[Trade] = None
        daily_pnl: dict = {}
        daily_loss = 0.0
        last_date = None

        for i in range(50, len(df)):              # Warm-up period = 50 bars
            bar = df.iloc[i]
            ts: datetime = df.index[i]
            bar_date = ts.date() if hasattr(ts, "date") else ts

            # Reset daily loss counter
            if bar_date != last_date:
                daily_loss = 0.0
                last_date = bar_date

            # Square-off at end of day
            sq_time = datetime.strptime(self._cfg.square_off_time, "%H:%M").time()
            if current_trade and hasattr(ts, "time") and ts.time() >= sq_time:
                current_trade = self._close_trade(
                    current_trade, bar["close"], ts, "EOD", trades
                )
                pnl = current_trade.pnl - self._commission()
                capital += pnl
                daily_loss += pnl if pnl < 0 else 0
                daily_pnl[bar_date] = daily_pnl.get(bar_date, 0) + pnl
                equity = capital
                current_trade = None

            # Check SL / Target on open trade
            if current_trade:
                closed, reason = self._check_exit(current_trade, bar)
                if closed:
                    exit_price = self._get_exit_price(current_trade, bar, reason)
                    current_trade = self._close_trade(
                        current_trade, exit_price, ts, reason, trades
                    )
                    pnl = current_trade.pnl - self._commission()
                    capital += pnl
                    daily_loss += pnl if pnl < 0 else 0
                    daily_pnl[bar_date] = daily_pnl.get(bar_date, 0) + pnl
                    equity = capital
                    current_trade = None

            equity_series.append((ts, equity))

            # Skip if already in trade or daily loss limit hit
            if current_trade:
                continue
            if daily_loss <= -(capital * self._cfg.max_daily_loss_pct / 100):
                continue

            # Generate signal
            sub_df = df.iloc[: i + 1]
            signal: Signal = strategy.generate_signal(sub_df, symbol)

            if signal.signal_type == SignalType.NO_SIGNAL:
                continue

            # Simulate option premium
            premium = self._estimate_premium(bar, signal)
            if premium <= 0:
                continue

            # Entry with slippage
            entry_price = premium * (1 + self._cfg.slippage_pct / 100)
            sl = entry_price * (1 - self._cfg.sl_pct / 100)
            target = entry_price * (1 + self._cfg.target_pct / 100)

            lots = self._compute_lots(capital, entry_price, sl)
            qty = lots * self._cfg.lot_size
            cost = qty * entry_price + self._commission(lots)

            if cost > capital:
                logger.debug("Insufficient capital for trade at bar %d", i)
                continue

            capital -= cost

            current_trade = Trade(
                symbol=f"{symbol}_{signal.option_type.value if signal.option_type else 'CE'}",
                strategy_name=strategy.name,
                option_type=signal.option_type,
                entry_price=entry_price,
                exit_price=0.0,
                quantity=qty,
                entry_time=ts,
            )
            # Attach SL / Target as metadata
            current_trade.__dict__["_sl"] = sl
            current_trade.__dict__["_target"] = target

        # Close any remaining trade at end
        if current_trade and len(df) > 0:
            last_close = df.iloc[-1]["close"]
            current_trade = self._close_trade(
                current_trade, last_close, df.index[-1], "EOD", trades
            )
            capital += current_trade.pnl - self._commission()

        # Build result
        eq_index = [t for t, _ in equity_series]
        eq_values = [v for _, v in equity_series]
        result.trades = trades
        result.equity_curve = pd.Series(eq_values, index=eq_index)
        result.daily_pnl = pd.Series(daily_pnl)
        result.metrics = self._compute_metrics(trades, result.equity_curve, self._cfg.initial_capital)

        logger.info(
            "Backtest complete | trades=%d | net_pnl=%.2f | sharpe=%.2f",
            len(trades), result.metrics.total_pnl, result.metrics.sharpe_ratio
        )
        return result

    # ── Trade Management ──────────────────────────────────────────

    def _check_exit(self, trade: Trade, bar: pd.Series) -> tuple[bool, str]:
        sl = trade.__dict__.get("_sl", 0)
        target = trade.__dict__.get("_target", float("inf"))
        if bar["low"] <= sl:
            return True, "STOP_LOSS"
        if bar["high"] >= target:
            return True, "TARGET"
        return False, ""

    def _get_exit_price(self, trade: Trade, bar: pd.Series, reason: str) -> float:
        if reason == "STOP_LOSS":
            return trade.__dict__.get("_sl", bar["close"]) * (1 - self._cfg.slippage_pct / 100)
        if reason == "TARGET":
            return trade.__dict__.get("_target", bar["close"]) * (1 - self._cfg.slippage_pct / 100)
        return bar["close"]

    @staticmethod
    def _close_trade(
        trade: Trade,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        trades: List[Trade],
    ) -> Trade:
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = reason
        trade.pnl = (exit_price - trade.entry_price) * trade.quantity
        if trade.entry_price > 0:
            trade.pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        trades.append(trade)
        return trade

    def _estimate_premium(self, bar: pd.Series, signal: Signal) -> float:
        """Estimate option premium from ATR if not provided."""
        if signal.entry_price and signal.entry_price > 0:
            return signal.entry_price
        atr_val = bar.get("atr", (bar["high"] - bar["low"]))
        return max(10.0, atr_val * self._cfg.atr_premium_multiplier)

    def _compute_lots(self, capital: float, entry_price: float, sl: float) -> int:
        risk_per_unit = max(0.1, entry_price - sl)
        max_risk = capital * 0.02   # Risk 2% of capital
        raw_lots = int(max_risk / (risk_per_unit * self._cfg.lot_size))
        return max(1, min(raw_lots, 10))

    def _commission(self, lots: int = 1) -> float:
        return lots * self._cfg.commission_per_lot

    # ── Performance Metrics ───────────────────────────────────────

    @staticmethod
    def _compute_metrics(
        trades: List[Trade],
        equity: pd.Series,
        initial_capital: float,
    ) -> PerformanceMetrics:
        m = PerformanceMetrics()
        if not trades:
            return m

        m.total_trades = len(trades)
        pnls = [t.pnl for t in trades]

        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        m.winning_trades = len(winners)
        m.losing_trades = len(losers)
        m.total_pnl = sum(pnls)
        m.gross_profit = sum(winners) if winners else 0.0
        m.gross_loss = sum(losers) if losers else 0.0
        m.win_rate = m.winning_trades / m.total_trades * 100
        m.avg_profit = np.mean(winners) if winners else 0.0
        m.avg_loss = np.mean(losers) if losers else 0.0
        m.profit_factor = (m.gross_profit / abs(m.gross_loss)) if m.gross_loss != 0 else float("inf")
        m.expectancy = (
            (m.win_rate / 100 * m.avg_profit) +
            ((1 - m.win_rate / 100) * m.avg_loss)
        )

        # Drawdown
        if not equity.empty:
            peak = equity.cummax()
            drawdown = equity - peak
            m.max_drawdown = drawdown.min()
            m.max_drawdown_pct = (drawdown / peak * 100).min()

        # Sharpe ratio (using daily returns)
        if len(equity) > 1:
            daily_returns = equity.resample("D").last().pct_change().dropna()
            if len(daily_returns) > 0 and daily_returns.std() > 0:
                excess = daily_returns.mean() - RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
                m.sharpe_ratio = round(
                    excess / daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR), 2
                )

                # Sortino (downside deviation)
                downside = daily_returns[daily_returns < 0]
                if len(downside) > 0 and downside.std() > 0:
                    m.sortino_ratio = round(
                        excess / downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR), 2
                    )

        # Calmar ratio
        if m.max_drawdown_pct != 0:
            annual_return = (m.total_pnl / initial_capital) * 100
            m.calmar_ratio = round(annual_return / abs(m.max_drawdown_pct), 2)

        # Consecutive wins / losses
        streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        for pnl in pnls:
            if pnl > 0:
                streak = max(1, streak + 1)
                max_win_streak = max(max_win_streak, streak)
            else:
                streak = min(-1, streak - 1)
                max_loss_streak = max(max_loss_streak, abs(streak))

        m.max_consecutive_wins = max_win_streak
        m.max_consecutive_losses = max_loss_streak

        # Avg holding period
        holding_times = []
        for t in trades:
            if t.entry_time and t.exit_time:
                diff = (t.exit_time - t.entry_time).total_seconds() / 60
                holding_times.append(diff)
        m.avg_holding_period_minutes = np.mean(holding_times) if holding_times else 0.0

        return m

    def print_report(self, result: BacktestResult) -> None:
        """Print a formatted performance report to stdout."""
        m = result.metrics
        sep = "─" * 55
        print(f"\n{'═' * 55}")
        print(f"  BACKTEST REPORT — {result.strategy_name}")
        print(f"{'═' * 55}")
        print(f"  Symbol      : {result.symbol}")
        print(f"  Period      : {result.start_date:%Y-%m-%d} → {result.end_date:%Y-%m-%d}")
        print(f"  Capital     : ₹{result.config.initial_capital:,.0f}")
        print(sep)
        print(f"  Total Trades         : {m.total_trades}")
        print(f"  Win Rate             : {m.win_rate:.1f}%")
        print(f"  Total P&L            : ₹{m.total_pnl:,.2f}")
        print(f"  Gross Profit         : ₹{m.gross_profit:,.2f}")
        print(f"  Gross Loss           : ₹{m.gross_loss:,.2f}")
        print(f"  Profit Factor        : {m.profit_factor:.2f}")
        print(f"  Avg Profit / Trade   : ₹{m.avg_profit:,.2f}")
        print(f"  Avg Loss / Trade     : ₹{m.avg_loss:,.2f}")
        print(sep)
        print(f"  Sharpe Ratio         : {m.sharpe_ratio:.2f}")
        print(f"  Sortino Ratio        : {m.sortino_ratio:.2f}")
        print(f"  Calmar Ratio         : {m.calmar_ratio:.2f}")
        print(f"  Max Drawdown         : ₹{m.max_drawdown:,.2f}  ({m.max_drawdown_pct:.1f}%)")
        print(f"  Max Consec. Wins     : {m.max_consecutive_wins}")
        print(f"  Max Consec. Losses   : {m.max_consecutive_losses}")
        print(f"  Avg Hold (min)       : {m.avg_holding_period_minutes:.1f}")
        print(f"{'═' * 55}\n")

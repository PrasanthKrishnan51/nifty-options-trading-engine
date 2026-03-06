"""
Unit tests for core components: indicators, strategies, risk, backtest.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import pandas as pd
import pytest
from datetime import datetime


def make_df(n=200, seed=1):
    np.random.seed(seed)
    close = 21500 + np.cumsum(np.random.normal(0, 12, n))
    dates = pd.date_range("2024-01-15 09:15", periods=n, freq="1min")
    return pd.DataFrame({
        "open":   close - np.abs(np.random.normal(5, 3, n)),
        "high":   close + np.abs(np.random.normal(15, 5, n)),
        "low":    close - np.abs(np.random.normal(15, 5, n)),
        "close":  close,
        "volume": np.random.randint(50_000, 300_000, n),
    }, index=dates)


# ── Indicators ────────────────────────────────────────────────────

class TestIndicators:
    def test_ema_shape(self):
        from indicators.technical import ema
        s = pd.Series(range(100), dtype=float)
        result = ema(s, 9)
        assert len(result) == 100

    def test_sma_values(self):
        from indicators.technical import sma
        s = pd.Series([1,2,3,4,5], dtype=float)
        result = sma(s, 3)
        assert abs(result.iloc[-1] - 4.0) < 1e-9

    def test_rsi_range(self):
        from indicators.technical import rsi
        df = make_df()
        r = rsi(df["close"])
        valid = r.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_atr_positive(self):
        from indicators.technical import atr
        df = make_df()
        result = atr(df).dropna()
        assert (result > 0).all()

    def test_macd_columns(self):
        from indicators.technical import macd
        df = make_df()
        result = macd(df["close"])
        assert set(result.columns) == {"macd", "signal", "histogram"}

    def test_bollinger_bands_columns(self):
        from indicators.technical import bollinger_bands
        df = make_df()
        bb = bollinger_bands(df["close"])
        assert "bb_upper" in bb.columns and "bb_lower" in bb.columns

    def test_vwap_shape(self):
        from indicators.technical import vwap
        df = make_df()
        v = vwap(df)
        assert len(v) == len(df)

    def test_supertrend_trend_values(self):
        from indicators.technical import supertrend
        df = make_df()
        st = supertrend(df)
        assert set(st["trend"].dropna().unique()).issubset({1, -1})

    def test_pivot_points(self):
        from indicators.technical import pivot_points
        pp = pivot_points(high=22100, low=21900, close=22000)
        assert "pivot" in pp and pp["r1"] > pp["pivot"] > pp["s1"]


# ── Strategies ────────────────────────────────────────────────────

class TestStrategies:
    def test_breakout_no_signal_on_small_df(self):
        from strategies.breakout_strategy import BreakoutStrategy
        strat = BreakoutStrategy()
        result = strat.generate_signal(make_df(5), "NIFTY")
        from core.models import SignalType
        assert result.signal_type == SignalType.NO_SIGNAL

    def test_ma_crossover_signal_type(self):
        from strategies.additional_strategies import MACrossoverStrategy
        from core.models import SignalType
        strat = MACrossoverStrategy(fast_period=5, slow_period=10)
        df = make_df(100)
        processed = strat.pre_process(df)
        sig = strat.generate_signal(processed, "NIFTY")
        assert sig.signal_type in list(SignalType)

    def test_vwap_strategy_runs(self):
        from strategies.additional_strategies import VWAPStrategy
        strat = VWAPStrategy()
        df = make_df(100)
        processed = strat.pre_process(df)
        sig = strat.generate_signal(processed, "NIFTY")
        assert sig is not None

    def test_momentum_strategy_runs(self):
        from strategies.additional_strategies import MomentumStrategy
        strat = MomentumStrategy()
        df = make_df(150)
        processed = strat.pre_process(df)
        sig = strat.generate_signal(processed, "NIFTY")
        assert sig is not None


# ── Risk Manager ──────────────────────────────────────────────────

class TestRiskManager:
    def test_can_trade_initially(self):
        from risk_management.risk_manager import RiskManager
        rm = RiskManager()
        ok, reason = rm.can_trade(500_000)
        assert ok

    def test_position_size_at_least_one_lot(self):
        from risk_management.risk_manager import RiskManager
        rm = RiskManager()
        lots = rm.calculate_position_size(500_000, 150.0, 105.0, 50, 0.8)
        assert lots >= 1

    def test_stop_loss_below_entry(self):
        from risk_management.risk_manager import RiskManager
        rm = RiskManager()
        sl = rm.compute_stop_loss(150.0, 150.0)
        assert sl < 150.0

    def test_target_above_entry(self):
        from risk_management.risk_manager import RiskManager
        rm = RiskManager()
        target = rm.compute_target(150.0, 150.0)
        assert target > 150.0

    def test_daily_loss_gate(self):
        from risk_management.risk_manager import RiskManager
        from core.models import Position
        rm = RiskManager()
        rm._daily_stats.realized_pnl = -12_000  # 2.4% of 500k
        ok, _ = rm.can_trade(500_000)
        assert not ok


# ── Backtester ────────────────────────────────────────────────────

class TestBacktester:
    def test_backtest_returns_trades(self):
        from backtesting.backtest_engine import BacktestEngine, BacktestConfig
        from strategies.breakout_strategy import BreakoutStrategy
        df = make_df(500)
        cfg = BacktestConfig(initial_capital=500_000)
        result = BacktestEngine(cfg).run(BreakoutStrategy(), df, "NIFTY")
        assert result.metrics is not None

    def test_win_rate_in_range(self):
        from backtesting.backtest_engine import BacktestEngine, BacktestConfig
        from strategies.additional_strategies import MACrossoverStrategy
        df = make_df(600)
        result = BacktestEngine().run(MACrossoverStrategy(), df, "NIFTY")
        if result.metrics.total_trades > 0:
            assert 0 <= result.metrics.win_rate <= 100


# ── Greeks ────────────────────────────────────────────────────────

class TestGreeks:
    def test_call_delta_range(self):
        from options.greeks import delta
        d = delta(S=22000, K=22000, T=0.027, r=0.067, sigma=0.15, option_type="CE")
        assert 0 <= d <= 1

    def test_put_delta_negative(self):
        from options.greeks import delta
        d = delta(S=22000, K=22000, T=0.027, r=0.067, sigma=0.15, option_type="PE")
        assert -1 <= d <= 0

    def test_gamma_positive(self):
        from options.greeks import gamma
        g = gamma(S=22000, K=22000, T=0.027, r=0.067, sigma=0.15)
        assert g > 0

    def test_iv_roundtrip(self):
        from options.greeks import option_price, implied_volatility
        sigma = 0.18
        price = option_price(22000, 22000, 0.027, 0.067, sigma, "CE")
        iv = implied_volatility(price, 22000, 22000, 0.027, 0.067, "CE")
        assert abs(iv - sigma) < 0.01

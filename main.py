"""
main.py — Application entry point.

Usage:
    python main.py live           # Start live / paper trading
    python main.py backtest       # Run strategy backtests
    python main.py api            # Start REST API server only
    python main.py demo           # Run with synthetic data (no broker needed)
"""

from __future__ import annotations

import sys
import threading
import logging

import uvicorn


def run_live() -> None:
    """Start the live trading engine with all strategies."""
    from live_trading.live_trader import LiveTrader
    from strategies.breakout_strategy import BreakoutStrategy
    from strategies.additional_strategies import (
        MACrossoverStrategy, VWAPStrategy, MomentumStrategy,
    )

    strategies = [
        BreakoutStrategy(orb_minutes=15, sl_atr_multiplier=1.5, target_atr_multiplier=3.0),
        MACrossoverStrategy(fast_period=9, slow_period=21),
        VWAPStrategy(deviation_threshold_pct=0.3),
        MomentumStrategy(macd_fast=12, macd_slow=26),
    ]

    trader = LiveTrader(strategies=strategies, tick_interval=60)

    # Start API in background thread
    from api.routes import app, set_live_trader
    set_live_trader(trader)

    api_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": "0.0.0.0", "port": 8000, "log_level": "warning"},
        daemon=True,
    )
    api_thread.start()

    trader.start()


def run_backtest() -> None:
    """Run backtests for all strategies on synthetic data."""
    import numpy as np
    import pandas as pd
    from datetime import datetime, timedelta

    from backtesting.backtest_engine import BacktestEngine, BacktestConfig
    from strategies.breakout_strategy import BreakoutStrategy
    from strategies.additional_strategies import MACrossoverStrategy, MomentumStrategy

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Generating synthetic OHLCV data for backtest...")

    # Generate realistic synthetic NIFTY-like data
    np.random.seed(42)
    n = 5000
    dates = pd.date_range("2023-01-02 09:15", periods=n, freq="1min")
    close = 18000 + np.cumsum(np.random.normal(0, 15, n))
    high = close + np.abs(np.random.normal(20, 10, n))
    low = close - np.abs(np.random.normal(20, 10, n))
    open_ = close + np.random.normal(0, 8, n)
    volume = np.random.randint(100_000, 500_000, n)

    df = pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    }, index=dates)

    bt_cfg = BacktestConfig(initial_capital=500_000, lot_size=50)
    engine = BacktestEngine(bt_cfg)

    strategies = [
        BreakoutStrategy(),
        MACrossoverStrategy(),
        MomentumStrategy(),
    ]

    for strategy in strategies:
        result = engine.run(strategy, df.copy(), symbol="NIFTY")
        engine.print_report(result)


def run_api() -> None:
    """Start only the REST API server."""
    from api.routes import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


def run_demo() -> None:
    """Run a quick demo showing signal generation on synthetic data."""
    import numpy as np
    import pandas as pd
    from logging_module.logger import setup_logging
    from strategies.breakout_strategy import BreakoutStrategy
    from strategies.additional_strategies import MACrossoverStrategy, VWAPStrategy, MomentumStrategy

    setup_logging(level="INFO")
    logger = logging.getLogger("demo")

    # Synthetic data
    np.random.seed(1)
    n = 200
    dates = pd.date_range("2024-01-15 09:15", periods=n, freq="1min")
    close = 21500 + np.cumsum(np.random.normal(0.5, 12, n))
    df = pd.DataFrame({
        "open": close - np.abs(np.random.normal(5, 3, n)),
        "high": close + np.abs(np.random.normal(15, 5, n)),
        "low": close - np.abs(np.random.normal(15, 5, n)),
        "close": close,
        "volume": np.random.randint(50_000, 300_000, n),
    }, index=dates)

    strategies = [
        BreakoutStrategy(orb_minutes=5),
        MACrossoverStrategy(fast_period=5, slow_period=13),
        VWAPStrategy(),
        MomentumStrategy(),
    ]

    logger.info("\n%s", "=" * 60)
    logger.info("  DEMO: Signal Generation on Synthetic NIFTY Data")
    logger.info("=" * 60)

    for strategy in strategies:
        processed = strategy.pre_process(df)
        signal = strategy.generate_signal(processed, "NIFTY")
        logger.info(
            "%-25s → %-12s conf=%.2f",
            strategy.name, signal.signal_type.value, signal.confidence
        )
        if signal.entry_price:
            logger.info(
                "  entry=%.2f  SL=%.2f  target=%.2f",
                signal.entry_price,
                signal.stop_loss or 0,
                signal.target or 0,
            )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"

    if cmd == "live":
        run_live()
    elif cmd == "backtest":
        run_backtest()
    elif cmd == "api":
        run_api()
    elif cmd == "demo":
        run_demo()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python main.py [live|backtest|api|demo]")
        sys.exit(1)

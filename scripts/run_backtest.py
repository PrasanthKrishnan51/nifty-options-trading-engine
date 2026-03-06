#!/usr/bin/env python3
"""
CLI Backtest Runner.

Usage:
    python scripts/run_backtest.py --strategy breakout --days 90 --capital 500000
    python scripts/run_backtest.py --strategy all
"""
import argparse, sys, os, logging
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.backtest_engine import BacktestEngine, BacktestConfig
from strategies.breakout_strategy import BreakoutStrategy
from strategies.additional_strategies import MACrossoverStrategy, VWAPStrategy, MomentumStrategy
from logging_module.logger import setup_logging

STRATEGIES = {
    "breakout":  lambda: BreakoutStrategy(),
    "ma":        lambda: MACrossoverStrategy(),
    "vwap":      lambda: VWAPStrategy(),
    "momentum":  lambda: MomentumStrategy(),
}


def make_synthetic(days: int, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    n = days * 375
    dates = pd.date_range("2024-01-02 09:15", periods=n, freq="1min")
    close = 21500 + np.cumsum(np.random.normal(0.2, 12, n))
    return pd.DataFrame({
        "open":   close - np.abs(np.random.normal(5, 3, n)),
        "high":   close + np.abs(np.random.normal(15, 5, n)),
        "low":    close - np.abs(np.random.normal(15, 5, n)),
        "close":  close,
        "volume": np.random.randint(50_000, 300_000, n),
    }, index=dates)


def main():
    parser = argparse.ArgumentParser(description="Backtest Runner")
    parser.add_argument("--strategy", default="all", choices=list(STRATEGIES.keys()) + ["all"])
    parser.add_argument("--days",    type=int,   default=90)
    parser.add_argument("--capital", type=float, default=500_000)
    parser.add_argument("--sl-pct",     type=float, default=30.0)
    parser.add_argument("--target-pct", type=float, default=60.0)
    args = parser.parse_args()

    setup_logging("INFO")
    logger = logging.getLogger("backtest_runner")
    logger.info("Generating %d days of synthetic data...", args.days)

    df = make_synthetic(args.days)
    cfg = BacktestConfig(initial_capital=args.capital, sl_pct=args.sl_pct, target_pct=args.target_pct)
    engine = BacktestEngine(cfg)

    to_run = STRATEGIES if args.strategy == "all" else {args.strategy: STRATEGIES[args.strategy]}
    for name, factory in to_run.items():
        result = engine.run(factory(), df.copy(), symbol="NIFTY")
        engine.print_report(result)

if __name__ == "__main__":
    main()

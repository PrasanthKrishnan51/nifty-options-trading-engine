"""
live_runner.py — compatibility shim. Use live_trading/live_trader.py instead.
"""
from live_trading.live_trader import LiveTrader
__all__ = ["LiveTrader"]

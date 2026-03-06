"""
Abstract Base Broker.

Every concrete broker (Zerodha, AngelOne, Fyers, Upstox) must implement
all abstract methods defined here so that the rest of the system remains
100% broker-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from core.models import Order, OrderStatus, Position, Tick


class BaseBroker(ABC):
    """
    Abstract broker interface.

    Subclasses must implement every @abstractmethod.
    Non-abstract helpers (is_connected, etc.) are inherited as-is.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._connected: bool = False
        self._tick_callbacks: List[Callable[[Tick], None]] = []

    # ── Identity ─────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Connection ───────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Authenticate and establish connection. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully close the connection."""

    # ── Market Data ──────────────────────────────────────────────

    @abstractmethod
    def get_quote(self, symbol: str, exchange: str = "NSE") -> Optional[Tick]:
        """Return a real-time full quote (LTP, bid, ask, OI, volume)."""

    @abstractmethod
    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Optional[float]:
        """Return last traded price only."""

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        from_date: datetime,
        to_date: datetime,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data.

        Returns DataFrame with columns: open, high, low, close, volume.
        Index must be a DatetimeIndex sorted ascending.
        """

    @abstractmethod
    def get_option_chain(
        self, underlying: str, expiry: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch option chain for the given underlying and expiry.

        Each dict should contain:
          strike, option_type, ltp, bid, ask, iv,
          delta, theta, vega, gamma, oi, volume, tradingsymbol.
        """

    # ── Orders ───────────────────────────────────────────────────

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """
        Submit an order to the exchange.

        Mutates and returns the order with broker_order_id and status set.
        """

    @abstractmethod
    def modify_order(self, order: Order) -> Order:
        """Modify an open order (price / qty / type)."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True on success."""

    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderStatus:
        """Return the current status of an order."""

    @abstractmethod
    def get_orders(self) -> List[Order]:
        """Return all orders for today's session."""

    # ── Positions & Portfolio ─────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Return all open intraday positions."""

    @abstractmethod
    def get_portfolio(self) -> Dict[str, Any]:
        """Return combined holdings + positions summary."""

    @abstractmethod
    def get_funds(self) -> Dict[str, float]:
        """Return available, used and total margin/funds."""

    # ── WebSocket Streaming ───────────────────────────────────────

    @abstractmethod
    def subscribe(
        self, symbols: List[str], callback: Callable[[Tick], None]
    ) -> None:
        """Subscribe to live market data ticks."""

    @abstractmethod
    def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from live ticks for given symbols."""

    # ── Optional helpers (override if broker supports) ────────────

    def get_market_status(self) -> Dict[str, Any]:
        """Check whether the market is currently open."""
        return {}

    def get_trades(self) -> List[Dict[str, Any]]:
        """Return executed trades for today."""
        return []

    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Return state-change history for a specific order."""
        return []

    def get_required_margin(self, *args, **kwargs) -> Optional[float]:
        """Calculate margin required for a potential order."""
        return None

    def get_brokerage(self, *args, **kwargs) -> Optional[Dict[str, float]]:
        """Return brokerage and statutory charges breakdown."""
        return None

    def get_profile(self) -> Dict[str, Any]:
        """Return the authenticated user's profile."""
        return {}

    # ── Internal helpers ──────────────────────────────────────────

    def _fire_tick(self, tick: Tick) -> None:
        """Dispatch a tick to all registered callbacks."""
        for cb in self._tick_callbacks:
            try:
                cb(tick)
            except Exception:
                pass

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"{self.__class__.__name__}(broker={self._name}, status={status})"

"""
Broker factory — returns the correct broker adapter based on configuration.

Supported brokers:
  - zerodha   (Zerodha KiteConnect)
  - upstox    (Upstox API v2) 
"""

from __future__ import annotations

import logging
from typing import Optional

from broker.base_broker import BaseBroker
from config.settings import config

logger = logging.getLogger(__name__)

_SUPPORTED_BROKERS = ("zerodha", "upstox")


def get_broker(broker_name: Optional[str] = None) -> BaseBroker:
    """
    Instantiate and return the configured broker adapter.

    Parameters
    ----------
    broker_name : str, optional
        Override the broker in config. One of: zerodha | upstox

    Returns
    -------
    BaseBroker
        A ready-to-use concrete broker implementation.

    Raises
    ------
    ValueError
        If an unknown broker name is supplied.
    """
    name = (broker_name or config.trading.broker).strip().lower()

    if name == "upstox":
        from broker.upstox.upstox_broker import UpstoxBroker
        logger.info("Broker: Upstox API v2")
        return UpstoxBroker()

    raise ValueError(
        f"Unknown broker: {name!r}. "
        f"Supported brokers: {', '.join(_SUPPORTED_BROKERS)}"
    )


def list_brokers() -> list[str]:
    """Return the list of all supported broker names."""
    return list(_SUPPORTED_BROKERS)

"""Broker factory — returns the correct broker adapter based on config."""
from __future__ import annotations
import logging
from typing import Optional
from broker.base_broker import BaseBroker
from config.settings import config

logger = logging.getLogger(__name__)
_SUPPORTED_BROKERS = ("zerodha", "angelone", "fyers", "upstox")


def get_broker(broker_name: Optional[str] = None) -> BaseBroker:
    name = (broker_name or config.trading.broker).strip().lower()
    if name == "upstox":
        from broker.upstox.upstox_broker import UpstoxBroker
        logger.info("Broker: Upstox API v2"); return UpstoxBroker()
    if name == "zerodha":
        from broker.zerodha.kite_broker import ZerodhaBroker
        logger.info("Broker: Zerodha KiteConnect"); return ZerodhaBroker()
    if name == "angelone":
        from broker.angelone.angel_broker import AngelOneBroker
        logger.info("Broker: AngelOne SmartAPI"); return AngelOneBroker()
    if name == "fyers":
        from broker.fyers.fyers_broker import FyersBroker
        logger.info("Broker: Fyers API v3"); return FyersBroker()
    raise ValueError(f"Unknown broker: {name!r}. Supported: {', '.join(_SUPPORTED_BROKERS)}")


def list_brokers() -> list:
    return list(_SUPPORTED_BROKERS)

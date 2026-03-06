# Compatibility shim
from logging_module.logger import setup_logging, get_trade_logger
import logging

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

__all__ = ["get_logger", "setup_logging", "get_trade_logger"]

"""
Logging setup — coloured console + rotating JSON file log + trade-specific logger.
"""
from __future__ import annotations
import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

_COLOURS = {
    "DEBUG":    "\033[36m",
    "INFO":     "\033[32m",
    "WARNING":  "\033[33m",
    "ERROR":    "\033[31m",
    "CRITICAL": "\033[35m",
    "RESET":    "\033[0m",
}

class _ColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, "")
        reset  = _COLOURS["RESET"]
        record.levelname = f"{colour}{record.levelname:<8}{reset}"
        return super().format(record)

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts":      datetime.utcnow().isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    """
    Configure root logger with:
      - Coloured StreamHandler → stdout
      - RotatingFileHandler (JSON) → logs/trading.log
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    if root.handlers:
        root.handlers.clear()

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(log_level)
    ch.setFormatter(_ColourFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(ch)

    # File handler (JSON, 10 MB, 5 backups)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        f"{log_dir}/trading.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_JsonFormatter())
    root.addHandler(fh)


def get_trade_logger(log_dir: str = "logs") -> logging.Logger:
    """Separate logger that writes only trade events to trades.log."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    tlogger = logging.getLogger("trades")
    if not tlogger.handlers:
        fh = logging.handlers.RotatingFileHandler(
            f"{log_dir}/trades.log", maxBytes=5 * 1024 * 1024, backupCount=10
        )
        fh.setFormatter(_JsonFormatter())
        tlogger.addHandler(fh)
        tlogger.propagate = False
    return tlogger

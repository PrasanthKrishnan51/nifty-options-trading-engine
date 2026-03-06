"""
Event Engine — lightweight pub/sub bus for decoupling system components.

Components publish events; subscribers receive them asynchronously
in a background thread so the main loop is never blocked.
"""
from __future__ import annotations
import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    TICK        = "TICK"
    SIGNAL      = "SIGNAL"
    ORDER_PLACE = "ORDER_PLACE"
    ORDER_UPDATE= "ORDER_UPDATE"
    TRADE_OPEN  = "TRADE_OPEN"
    TRADE_CLOSE = "TRADE_CLOSE"
    RISK_BREACH = "RISK_BREACH"
    ERROR       = "ERROR"
    EOD         = "EOD"


@dataclass
class Event:
    type: EventType
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


class EventEngine:
    """
    Thread-safe event bus.

    Usage:
        engine = EventEngine()
        engine.subscribe(EventType.SIGNAL, my_handler)
        engine.start()
        engine.publish(Event(EventType.SIGNAL, signal_obj, source="BreakoutStrategy"))
        engine.stop()
    """

    def __init__(self, queue_size: int = 1000) -> None:
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=queue_size)
        self._handlers: Dict[EventType, List[Callable[[Event], None]]] = {
            et: [] for et in EventType
        }
        self._thread: threading.Thread | None = None
        self._running = False

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("EventEngine: %s subscribed to %s", handler.__name__, event_type)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("EventEngine: queue full, dropping event %s", event.type)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="EventEngine")
        self._thread.start()
        logger.info("EventEngine started.")

    def stop(self) -> None:
        self._running = False
        self._queue.put_nowait(Event(EventType.EOD, None, source="engine"))
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("EventEngine stopped.")

    def _run(self) -> None:
        while self._running:
            try:
                event = self._queue.get(timeout=1)
                if event.type == EventType.EOD and not self._running:
                    break
                for handler in self._handlers.get(event.type, []):
                    try:
                        handler(event)
                    except Exception as exc:
                        logger.exception("EventEngine handler %s raised: %s", handler.__name__, exc)
                self._queue.task_done()
            except queue.Empty:
                continue

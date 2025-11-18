"""Event bus utilities for real-time telegram streaming."""
from __future__ import annotations

import queue
import threading
from typing import Dict, List, Optional


class EventBus:
    def __init__(self) -> None:
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        consumer: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(consumer)
        return consumer

    def unsubscribe(self, consumer: queue.Queue) -> None:
        with self._lock:
            if consumer in self._subscribers:
                self._subscribers.remove(consumer)

    def publish(self, event: Dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for consumer in subscribers:
            try:
                consumer.put_nowait(event)
            except queue.Full:
                pass

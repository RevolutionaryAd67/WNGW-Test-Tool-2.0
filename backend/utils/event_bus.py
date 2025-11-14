"""Asynchronous event bus used for broadcasting events to WebSocket listeners."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Set


class EventBus:
    """Simple publish/subscribe event bus for asyncio tasks."""

    def __init__(self) -> None:
        self._queues: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        async with self._lock:
            for queue_set in self._queues.values():
                for queue in queue_set:
                    queue.put_nowait({"event": "shutdown"})
            self._queues.clear()
        self._running = False

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues[channel].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._queues[channel].discard(queue)

    async def publish(self, channel: str, message: dict) -> None:
        if not self._running:
            return
        async with self._lock:
            queues = list(self._queues[channel])
        for queue in queues:
            await queue.put(message)


event_bus = EventBus()

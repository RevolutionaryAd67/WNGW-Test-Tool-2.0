from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator, Dict, List


class EventBus:
    """Simple in-memory pub/sub system for backend events."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> AsyncIterator[Any]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers[channel].append(queue)
        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            async with self._lock:
                if queue in self._subscribers[channel]:
                    self._subscribers[channel].remove(queue)

    async def publish(self, channel: str, message: Any) -> None:
        async with self._lock:
            subscribers = list(self._subscribers[channel])
        for queue in subscribers:
            await queue.put(message)

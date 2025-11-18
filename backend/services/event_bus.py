"""Simple in-memory pub/sub event bus for distributing backend events."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator, Dict, List


class EventBus:
    """Async pub/sub bus used to forward events to WebSocket connections."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, message: Dict[str, Any]) -> None:
        """Publish a message to all listeners of *channel*."""
        async with self._lock:
            queues = list(self._subscribers.get(channel, []))
        for queue in queues:
            await queue.put(message)

    async def subscribe(self, channel: str) -> AsyncIterator[Dict[str, Any]]:
        """Yield messages for *channel* until the iterator is closed."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers[channel].append(queue)

        try:
            while True:
                message = await queue.get()
                yield message
        finally:
            await self._remove_queue(channel, queue)

    async def get_queue(self, channel: str) -> asyncio.Queue[Dict[str, Any]]:
        """Return a queue that receives events for *channel*."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers[channel].append(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[Any]) -> None:
        await self._remove_queue(channel, queue)

    async def _remove_queue(self, channel: str, queue: asyncio.Queue[Any]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(channel)
            if not subscribers:
                return
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._subscribers.pop(channel, None)


async def forward_events(queue: asyncio.Queue[Dict[str, Any]], websocket_send) -> None:
    """Forward events from *queue* to a WebSocket send callable."""
    try:
        while True:
            event = await queue.get()
            await websocket_send(event)
    finally:
        # Ensure queue is drained to avoid pending tasks.
        while not queue.empty():
            queue.get_nowait()
            queue.task_done()

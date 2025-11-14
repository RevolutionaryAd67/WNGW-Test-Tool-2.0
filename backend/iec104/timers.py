"""Simple asyncio timer helpers for IEC-104 state handling."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

TimerCallback = Callable[[], Awaitable[None]]


@dataclass
class IECTimer:
    name: str
    timeout: float
    callback: TimerCallback
    _task: Optional[asyncio.Task] = field(default=None, init=False, repr=False)

    def start(self) -> None:
        self.cancel()
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self.timeout)
            await self.callback()
        except asyncio.CancelledError:  # pragma: no cover - behaviour by design
            return

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None


class TimerGroup:
    def __init__(self, t1: float, t2: float, t3: float, callback: TimerCallback) -> None:
        self.t1 = IECTimer("T1", t1, callback)
        self.t2 = IECTimer("T2", t2, callback)
        self.t3 = IECTimer("T3", t3, callback)

    def start_all(self) -> None:
        self.t1.start()
        self.t2.start()
        self.t3.start()

    def cancel_all(self) -> None:
        self.t1.cancel()
        self.t2.cancel()
        self.t3.cancel()

"""Simplified IEC-104 session state machine."""
from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional


class ConnectionState(Enum):
    IDLE = auto()
    START_SENT = auto()
    RUNNING = auto()
    STOP_SENT = auto()


class IECStateMachine:
    def __init__(self, on_state_change: Callable[[ConnectionState], None]) -> None:
        self.state = ConnectionState.IDLE
        self._callback = on_state_change

    def start(self) -> None:
        self.state = ConnectionState.START_SENT
        self._callback(self.state)

    def confirm_start(self) -> None:
        self.state = ConnectionState.RUNNING
        self._callback(self.state)

    def stop(self) -> None:
        self.state = ConnectionState.STOP_SENT
        self._callback(self.state)

    def reset(self) -> None:
        self.state = ConnectionState.IDLE
        self._callback(self.state)

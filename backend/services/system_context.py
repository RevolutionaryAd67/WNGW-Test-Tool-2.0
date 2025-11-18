"""Shared runtime context for routers and services."""
from __future__ import annotations

from typing import Optional

from .event_bus import EventBus

_event_bus: Optional[EventBus] = None


def set_event_bus(event_bus: EventBus) -> None:
    global _event_bus
    _event_bus = event_bus


def get_event_bus() -> EventBus:
    if _event_bus is None:
        raise RuntimeError("Event bus has not been initialized")
    return _event_bus

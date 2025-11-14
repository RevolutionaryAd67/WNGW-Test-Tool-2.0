"""Simplified IEC-104 client/master implementation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.config.settings_manager import settings_manager
from backend.iec104 import frame_encoder
from backend.iec104.flowcontrol import FlowControl
from backend.iec104.state_machine import ConnectionState, IECStateMachine
from backend.logging.log_formatter import export_log_lines
from backend.logging.logger import get_logger
from backend.utils.event_bus import event_bus
from backend.utils.file_utils import write_lines

CLIENT_CHANNEL = "client"
SYSTEM_CHANNEL = "system"

logger = get_logger(__name__)


@dataclass
class ClientState:
    active: bool = False
    sequence: int = 0
    frames: List[Dict] = field(default_factory=list)
    auto_scroll: bool = True
    sync_scroll: bool = False


class IEC104Client:
    """High level client controller with placeholder networking."""

    def __init__(self) -> None:
        self.state = ClientState()
        self.flow = FlowControl()
        self.settings = settings_manager.load("client")
        self._state_machine = IECStateMachine(self._on_state_change)
        self._start_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self.state.active:
            return
        logger.info("Starting IEC-104 client placeholder")
        self.state.active = True
        self._state_machine.start()
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "out", "STARTDT ACT"))
        self._start_task = asyncio.create_task(self._confirm_start())
        await self._notify_footer(True)

    async def _confirm_start(self) -> None:
        await asyncio.sleep(0.2)
        self._state_machine.confirm_start()
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "in", "STARTDT CON"))

    async def stop(self) -> None:
        if not self.state.active:
            return
        logger.info("Stopping IEC-104 client placeholder")
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "out", "STOPDT ACT"))
        self._state_machine.stop()
        self.state.active = False
        self.flow.reset()
        await self._notify_footer(False)
        if self._start_task:
            self._start_task.cancel()
            self._start_task = None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    async def send_general_interrogation(self) -> Dict:
        if not self.state.active or self._state_machine.state != ConnectionState.RUNNING:
            raise RuntimeError("Client not active")
        ca = self.settings.get("partner", {}).get("ca", 1)
        frame = frame_encoder.build_gi_frame(
            self._next_sequence(),
            "out",
            ca,
            "GENERALABFRAGE ACT",
            frame_encoder.COT_ACTIVATION,
        )
        await self._publish_frame(frame)
        await event_bus.publish(CLIENT_CHANNEL, {"event": "gi_sent"})
        return frame

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------
    async def _publish_frame(self, frame: Dict) -> None:
        self.state.frames.append(frame)
        await event_bus.publish(CLIENT_CHANNEL, frame)

    def _next_sequence(self) -> int:
        self.state.sequence += 1
        return self.state.sequence

    def clear_log(self) -> None:
        self.state.frames.clear()
        self.state.sequence = 0

    def export_log(self, path: Path) -> None:
        write_lines(path, export_log_lines(self.state.frames))

    # ------------------------------------------------------------------
    async def _notify_footer(self, active: bool) -> None:
        await event_bus.publish(
            SYSTEM_CHANNEL,
            {
                "event": "client_status",
                "active": active,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def _on_state_change(self, state: ConnectionState) -> None:
        logger.debug("Client state changed: %s", state)

    def reload_settings(self) -> None:
        self.settings = settings_manager.load("client")


client_master = IEC104Client()

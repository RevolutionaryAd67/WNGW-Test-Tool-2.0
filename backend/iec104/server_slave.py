"""Simplified IEC-104 server/slave implementation."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.config.settings_manager import settings_manager
from backend.iec104 import frame_encoder
from backend.iec104.flowcontrol import FlowControl
from backend.iec104.state_machine import ConnectionState, IECStateMachine
from backend.logging.log_formatter import export_log_lines
from backend.logging.logger import get_logger
from backend.utils.event_bus import event_bus
from backend.utils.file_utils import write_lines

SERVER_CHANNEL = "server"
SYSTEM_CHANNEL = "system"

logger = get_logger(__name__)


@dataclass
class ServerState:
    active: bool = False
    sequence: int = 0
    frames: List[Dict] = field(default_factory=list)


class IEC104Server:
    def __init__(self) -> None:
        self.state = ServerState()
        self.flow = FlowControl()
        self.settings = settings_manager.load("server")
        self._state_machine = IECStateMachine(self._on_state_change)
        self._listener_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.state.active:
            return
        logger.info("Starting IEC-104 server placeholder")
        self.state.active = True
        self._state_machine.start()
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "in", "STARTDT ACT"))
        await asyncio.sleep(0.2)
        self._state_machine.confirm_start()
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "out", "STARTDT CON"))
        await self._notify_footer(True)

    async def stop(self) -> None:
        if not self.state.active:
            return
        logger.info("Stopping IEC-104 server placeholder")
        await self._publish_frame(frame_encoder.build_u_frame(self._next_sequence(), "in", "STOPDT ACT"))
        self._state_machine.stop()
        self.state.active = False
        self.flow.reset()
        await self._notify_footer(False)

    async def handle_external_gi(self) -> None:
        if not self.state.active or self._state_machine.state != ConnectionState.RUNNING:
            raise RuntimeError("Server not active")
        ca = self.settings.get("asdu", {}).get("ca", 1)
        con = frame_encoder.build_gi_frame(
            self._next_sequence(),
            "out",
            ca,
            "GENERALABFRAGE CON",
            frame_encoder.COT_CONFIRMATION,
        )
        end = frame_encoder.build_gi_frame(
            self._next_sequence(),
            "out",
            ca,
            "GENERALABFRAGE END",
            frame_encoder.COT_TERMINATION,
        )
        await self._publish_frame(con)
        await asyncio.sleep(0.1)
        await self._publish_frame(end)
        await event_bus.publish(SERVER_CHANNEL, {"event": "gi_replied"})

    async def register_external_gi(self) -> None:
        incoming = frame_encoder.build_gi_frame(
            self._next_sequence(),
            "in",
            self.settings.get("asdu", {}).get("ca", 1),
            "GENERALABFRAGE ACT",
            frame_encoder.COT_ACTIVATION,
        )
        await self._publish_frame(incoming)
        await event_bus.publish(SERVER_CHANNEL, {"event": "gi_received"})
        await self.handle_external_gi()

    async def _publish_frame(self, frame: Dict) -> None:
        self.state.frames.append(frame)
        await event_bus.publish(SERVER_CHANNEL, frame)

    def _next_sequence(self) -> int:
        self.state.sequence += 1
        return self.state.sequence

    def clear_log(self) -> None:
        self.state.frames.clear()
        self.state.sequence = 0

    def export_log(self, path: Path) -> None:
        write_lines(path, export_log_lines(self.state.frames))

    async def _notify_footer(self, active: bool) -> None:
        await event_bus.publish(
            SYSTEM_CHANNEL,
            {
                "event": "server_status",
                "active": active,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def _on_state_change(self, state: ConnectionState) -> None:
        logger.debug("Server state changed: %s", state)

    def reload_settings(self) -> None:
        self.settings = settings_manager.load("server")


server_slave = IEC104Server()

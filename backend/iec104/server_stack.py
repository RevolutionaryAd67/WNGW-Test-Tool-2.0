"""Simplified IEC-104 server/slave stack with independent control logic."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.services.logging_service import logging_service
from backend.services.system_context import get_event_bus


class ServerState(str, Enum):
    IDLE = "idle"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    SHUTTING_DOWN = "shutting_down"
    HALTED = "halted"


class ServerConnectionState(str, Enum):
    OFFLINE = "offline"
    LISTENING = "listening"
    ESTABLISHED = "established"


@dataclass
class ServerFlowControl:
    send_counter: int = 0
    recv_counter: int = 0
    k: int = 12
    w: int = 8


@dataclass
class ServerTimers:
    t1: float = 12.0
    t2: float = 8.0
    t3: float = 18.0
    _last_frame: float = field(default_factory=time.time)

    def mark(self) -> None:
        self._last_frame = time.time()

    def diagnostics(self) -> Dict[str, bool]:
        now = time.time()
        return {
            "t1": now - self._last_frame > self.t1,
            "t2": now - self._last_frame > self.t2,
            "t3": now - self._last_frame > self.t3,
        }


class IEC104ServerStack:
    def __init__(self) -> None:
        self.state = ServerState.HALTED
        self.timers = ServerTimers()
        self.flow = ServerFlowControl()
        self.outgoing_frames: List[str] = []
        self.incoming_asdu: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._logger = logging_service.get_logger(__name__)
        self._partner_ip = "127.0.0.1"
        self._partner_station = 1
        self._listen_ip = "0.0.0.0"
        self._listen_port = 2404
        self._station_address = 1
        self._connection_task: Optional[asyncio.Task[Any]] = None
        self._connection_state = ServerConnectionState.OFFLINE
        self._connected = False
        self._handshake_count = 0

    async def start(self) -> None:
        async with self._lock:
            if self.state in {ServerState.ACTIVE, ServerState.INITIALIZING}:
                return
            self.state = ServerState.INITIALIZING
            await asyncio.sleep(0.2)
            self.state = ServerState.ACTIVE
            self.timers.mark()
            self._handshake_count = 0
            self._logger.info("IEC104 server stack active")
            self._start_connection_loop()

    async def stop(self) -> None:
        async with self._lock:
            if self.state == ServerState.HALTED:
                return
            self.state = ServerState.SHUTTING_DOWN
            await self._stop_connection_loop()
            await asyncio.sleep(0.2)
            self.state = ServerState.HALTED
            self._logger.info("IEC104 server stack halted")

    async def reset(self) -> None:
        async with self._lock:
            await self._stop_connection_loop()
            self.flow = ServerFlowControl()
            self.timers = ServerTimers()
            self.outgoing_frames.clear()
            self.incoming_asdu.clear()
            self.state = ServerState.HALTED
            self._logger.info("IEC104 server stack reset")

    async def send_asdu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            if self.state != ServerState.ACTIVE:
                raise RuntimeError("Server stack is not active")
            self.flow.send_counter = (self.flow.send_counter + 1) % 32768
            asdu_repr = self._format_asdu(payload)
            transmission = {
                "frame": asdu_repr,
                "seq": self.flow.send_counter,
                "destination": {
                    "ip": self._partner_ip,
                    "station_address": self._partner_station,
                },
                "source": {
                    "ip": self._listen_ip,
                    "port": self._listen_port,
                    "station_address": self._station_address,
                },
                "payload": payload,
            }
            self.outgoing_frames.append(asdu_repr)
            self.timers.mark()
            return transmission

    def simulate_packet(self) -> None:
        if self.state != ServerState.ACTIVE:
            return
        pkt_type = random.choice(["I", "S", "U"])
        payload = {"type": pkt_type, "value": random.randint(1, 1000)}
        if pkt_type == "I":
            self.flow.recv_counter = (self.flow.recv_counter + 1) % 32768
            self.incoming_asdu.append(payload)
        frame = f"{pkt_type}-FRAME-{payload['value']}"
        self.outgoing_frames.append(frame)
        self.timers.mark()

    def status(self) -> Dict[str, Any]:
        diagnostics = self.timers.diagnostics()
        return {
            "state": self.state.value,
            "timers": diagnostics,
            "flow": {
                "send": self.flow.send_counter,
                "recv": self.flow.recv_counter,
                "k": self.flow.k,
                "w": self.flow.w,
            },
            "outgoing": len(self.outgoing_frames),
            "incoming": len(self.incoming_asdu),
            "network": {
                "destination": {
                    "ip": self._partner_ip,
                    "station_address": self._partner_station,
                },
                "listening": {
                    "ip": self._listen_ip,
                    "port": self._listen_port,
                    "station_address": self._station_address,
                },
            },
            "connection": {
                "state": self._connection_state.value,
                "connected": self._connected,
                "handshakes": self._handshake_count,
            },
        }

    def _format_asdu(self, payload: Dict[str, Any]) -> str:
        return f"ASDU-{self.flow.send_counter}-{payload.get('type','generic')}"

    def configure_network(
        self,
        *,
        partner_ip: str,
        partner_station: int,
        listen_ip: str,
        listen_port: int,
        station_address: int,
    ) -> None:
        self._partner_ip = partner_ip
        self._partner_station = partner_station
        self._listen_ip = listen_ip
        self._listen_port = listen_port
        self._station_address = station_address
        self._logger.info(
            "Server network configured: partner=%s/%s listen=%s:%s station=%s",
            partner_ip,
            partner_station,
            listen_ip,
            listen_port,
            station_address,
        )

    def _start_connection_loop(self) -> None:
        if self._connection_task and not self._connection_task.done():
            return
        self._connection_task = asyncio.create_task(self._connection_loop())

    async def _stop_connection_loop(self) -> None:
        if not self._connection_task:
            self._connection_state = ServerConnectionState.OFFLINE
            self._connected = False
            return
        task = self._connection_task
        self._connection_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._connection_state = ServerConnectionState.OFFLINE
            self._connected = False
            await self._publish_connection_event("offline", "server stopped listening")

    async def _connection_loop(self) -> None:
        try:
            while self.state == ServerState.ACTIVE:
                if not self._connected:
                    self._connection_state = ServerConnectionState.LISTENING
                    await self._publish_connection_event(
                        "listening",
                        f"awaiting partner {self._partner_ip}:{self._listen_port}",
                    )
                    await asyncio.sleep(0.5)
                    self._connected = True
                    self._connection_state = ServerConnectionState.ESTABLISHED
                    self._handshake_count += 1
                    await self._publish_connection_event(
                        "established",
                        "partner connection accepted",
                    )
                await asyncio.sleep(2.0)
                self.timers.mark()
        except asyncio.CancelledError:
            self._logger.debug("Server connection loop cancelled")
        finally:
            if self._connection_state != ServerConnectionState.OFFLINE:
                self._connected = False
                prev_state = self._connection_state
                self._connection_state = ServerConnectionState.LISTENING if self.state == ServerState.ACTIVE else ServerConnectionState.OFFLINE
                await self._publish_connection_event(
                    "listening" if self.state == ServerState.ACTIVE else "offline",
                    "connection loop ended" if prev_state != ServerConnectionState.OFFLINE else "server idle",
                )

    async def _publish_connection_event(self, state: str, message: str) -> None:
        try:
            bus = get_event_bus()
        except RuntimeError:
            return
        await bus.publish(
            "server",
            {
                "type": "connection",
                "state": state,
                "message": message,
                "status": self.status(),
            },
        )


server_stack = IEC104ServerStack()

"""Simplified but fully isolated IEC-104 client/master stack implementation."""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.services.logging_service import logging_service
from backend.services.system_context import get_event_bus


class ClientState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ClientConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class ClientFlowControl:
    send_seq: int = 0
    recv_seq: int = 0
    k: int = 12
    w: int = 8


@dataclass
class ClientTimers:
    t1: float = 15.0
    t2: float = 10.0
    t3: float = 20.0
    _last_activity: float = field(default_factory=time.time)

    def touch(self) -> None:
        self._last_activity = time.time()

    def expired(self) -> Dict[str, bool]:
        now = time.time()
        return {
            "t1": now - self._last_activity > self.t1,
            "t2": now - self._last_activity > self.t2,
            "t3": now - self._last_activity > self.t3,
        }


class IEC104ClientStack:
    """Imitates the behavior of a client/master stack for IEC-104."""

    def __init__(self) -> None:
        self.state = ClientState.STOPPED
        self.timers = ClientTimers()
        self.flow = ClientFlowControl()
        self.sent_asdu: List[Dict[str, Any]] = []
        self.received_frames: List[str] = []
        self._lock = asyncio.Lock()
        self._logger = logging_service.get_logger(__name__)
        self._partner_ip = "127.0.0.1"
        self._partner_station = 1
        self._listen_ip = "0.0.0.0"
        self._listen_port = 2404
        self._connection_task: Optional[asyncio.Task[Any]] = None
        self._connection_state = ClientConnectionState.DISCONNECTED
        self._connected = False
        self._connection_attempts = 0

    async def start(self) -> None:
        async with self._lock:
            if self.state in {ClientState.RUNNING, ClientState.STARTING}:
                return
            self.state = ClientState.STARTING
            await asyncio.sleep(0.1)  # simulate startup work
            self.state = ClientState.RUNNING
            self.timers.touch()
            self._connection_attempts = 0
            self._logger.info("IEC104 client stack started")
            self._start_connection_loop()

    async def stop(self) -> None:
        async with self._lock:
            if self.state == ClientState.STOPPED:
                return
            self.state = ClientState.STOPPING
            await self._stop_connection_loop()
            await asyncio.sleep(0.1)
            self.state = ClientState.STOPPED
            self._logger.info("IEC104 client stack stopped")

    async def reset(self) -> None:
        async with self._lock:
            await self._stop_connection_loop()
            self.flow = ClientFlowControl()
            self.timers = ClientTimers()
            self.sent_asdu.clear()
            self.received_frames.clear()
            self.state = ClientState.STOPPED
            self._logger.info("IEC104 client stack reset")

    async def send_asdu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            if self.state != ClientState.RUNNING:
                raise RuntimeError("Client stack not running")
            self.flow.send_seq = (self.flow.send_seq + 1) % 32768
            frame = self._encode_i_frame(payload)
            transmission = {
                "frame": frame,
                "seq": self.flow.send_seq,
                "destination": {
                    "ip": self._partner_ip,
                    "station_address": self._partner_station,
                },
                "source": {
                    "ip": self._listen_ip,
                    "port": self._listen_port,
                },
                "payload": payload,
            }
            self.sent_asdu.append(transmission)
            self.received_frames.append(frame)
            self.timers.touch()
            return transmission

    def simulate_network_activity(self) -> None:
        """Simulate receiving I, S, U frames by random generation."""
        if self.state != ClientState.RUNNING:
            return
        frame_type = random.choice(["I", "S", "U"])
        if frame_type == "I":
            self.flow.recv_seq = (self.flow.recv_seq + 1) % 32768
        self.received_frames.append(f"{frame_type}-FRAME-{random.randint(1, 999)}")
        self.timers.touch()

    def status(self) -> Dict[str, Any]:
        expired = self.timers.expired()
        return {
            "state": self.state.value,
            "timers": expired,
            "flow": {
                "send": self.flow.send_seq,
                "recv": self.flow.recv_seq,
                "k": self.flow.k,
                "w": self.flow.w,
            },
            "sent": len(self.sent_asdu),
            "received_frames": len(self.received_frames),
            "network": {
                "destination": {
                    "ip": self._partner_ip,
                    "station_address": self._partner_station,
                },
                "listening": {
                    "ip": self._listen_ip,
                    "port": self._listen_port,
                },
            },
            "connection": {
                "state": self._connection_state.value,
                "connected": self._connected,
                "attempts": self._connection_attempts,
            },
        }

    def _encode_i_frame(self, payload: Dict[str, Any]) -> str:
        return f"I-{self.flow.send_seq}-{payload.get('type','asdu')}"

    def configure_network(
        self,
        *,
        partner_ip: str,
        partner_station: int,
        listen_ip: str,
        listen_port: int,
    ) -> None:
        self._partner_ip = partner_ip
        self._partner_station = partner_station
        self._listen_ip = listen_ip
        self._listen_port = listen_port
        self._logger.info(
            "Client network configured: partner=%s/%s listen=%s:%s",
            partner_ip,
            partner_station,
            listen_ip,
            listen_port,
        )

    def _start_connection_loop(self) -> None:
        if self._connection_task and not self._connection_task.done():
            return
        self._connection_task = asyncio.create_task(self._connection_loop())

    async def _stop_connection_loop(self) -> None:
        if not self._connection_task:
            self._connection_state = ClientConnectionState.DISCONNECTED
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
            self._connection_state = ClientConnectionState.DISCONNECTED
            self._connected = False
            await self._publish_connection_event("disconnected", "client stopped")

    async def _connection_loop(self) -> None:
        try:
            while self.state == ClientState.RUNNING:
                if not self._connected:
                    self._connection_state = ClientConnectionState.CONNECTING
                    self._connection_attempts += 1
                    await self._publish_connection_event(
                        "connecting",
                        f"attempt {self._connection_attempts} to {self._partner_ip}:{self._partner_station}",
                    )
                    await asyncio.sleep(0.5)
                    self._connected = True
                    self._connection_state = ClientConnectionState.CONNECTED
                    await self._publish_connection_event(
                        "connected",
                        "TCP and IEC-104 link established",
                    )
                await asyncio.sleep(2.0)
                self.timers.touch()
        except asyncio.CancelledError:
            self._logger.debug("Client connection loop cancelled")
        finally:
            if self._connected or self._connection_state != ClientConnectionState.DISCONNECTED:
                self._connected = False
                self._connection_state = ClientConnectionState.DISCONNECTED
                await self._publish_connection_event("disconnected", "connection loop ended")

    async def _publish_connection_event(self, state: str, message: str) -> None:
        try:
            bus = get_event_bus()
        except RuntimeError:
            return
        await bus.publish(
            "client",
            {
                "type": "connection",
                "state": state,
                "message": message,
                "status": self.status(),
            },
        )


client_stack = IEC104ClientStack()

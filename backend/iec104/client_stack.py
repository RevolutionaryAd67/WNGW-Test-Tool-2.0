from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from backend.iec104.connection_profiles import ClientConnectionProfile

class ClientState(str, Enum):
    STOPPED = "stopped"
    STARTED = "started"
    CONNECTED = "connected"
    RUNNING = "running"


@dataclass
class ClientTimers:
    t1: float = 15.0
    t2: float = 10.0
    t3: float = 20.0
    last_t1_reset: float = field(default_factory=time.time)
    last_t2_reset: float = field(default_factory=time.time)
    last_t3_reset: float = field(default_factory=time.time)

    def reset(self) -> None:
        now = time.time()
        self.last_t1_reset = now
        self.last_t2_reset = now
        self.last_t3_reset = now


class IEC104ClientStack:
    """Simplified IEC-104 master stack with dedicated state machine."""

    def __init__(self) -> None:
        self.state = ClientState.STOPPED
        self.timers = ClientTimers()
        self.send_sequence = 0
        self.recv_sequence = 0
        self.k_window = 12
        self.w_window = 8
        self.sent_frames = 0
        self.received_frames = 0
        self.partner_ip = ""
        self.partner_station_address = ""
        self.listen_ip = ""
        self.listen_port: Optional[int] = None
        self.originator_address = ""
        self._connection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.connection_attempts = 0
        self.last_connection_established: Optional[float] = None

    def apply_connection_profile(self, profile: ClientConnectionProfile) -> None:
        self.partner_ip = profile.partner_ip
        self.partner_station_address = profile.partner_station_address
        self.listen_ip = profile.listen_ip
        self.listen_port = profile.listen_port
        self.originator_address = profile.originator_address

    def start(self) -> Dict[str, Any]:
        if self.state != ClientState.STOPPED:
            return self.status()
        self._stop_event.clear()
        self.state = ClientState.STARTED
        self.timers.reset()
        self._connection_thread = threading.Thread(
            target=self._connection_worker, name="iec104-client", daemon=True
        )
        self._connection_thread.start()
        self._negotiate_connection()
        return self.status()

    def _connection_worker(self) -> None:
        while not self._stop_event.is_set():
            if self.state == ClientState.RUNNING:
                self._maintain_connection()
            self._stop_event.wait(1.0)

    def _negotiate_connection(self) -> None:
        self.connection_attempts += 1
        self.state = ClientState.CONNECTED
        self._send_u_frame("STARTDT_ACT")
        self.state = ClientState.RUNNING
        self.last_connection_established = time.time()

    def _maintain_connection(self) -> None:
        if time.time() - self.timers.last_t3_reset >= self.timers.t3:
            self._send_u_frame("TESTFR_ACT")
        self.timers.reset()

    def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        if self._connection_thread and self._connection_thread.is_alive():
            self._connection_thread.join(timeout=1.0)
        self._connection_thread = None
        self.state = ClientState.STOPPED
        self.send_sequence = 0
        self.recv_sequence = 0
        self.sent_frames = 0
        self.received_frames = 0
        return self.status()

    def reset(self) -> Dict[str, Any]:
        self.timers.reset()
        self.send_sequence = 0
        self.recv_sequence = 0
        return self.status()

    def _send_u_frame(self, command: str) -> Dict[str, Any]:
        frame = {"type": "U", "command": command, "timestamp": time.time()}
        self.sent_frames += 1
        return frame

    def _send_s_frame(self) -> Dict[str, Any]:
        frame = {"type": "S", "seq": self.recv_sequence, "timestamp": time.time()}
        self.sent_frames += 1
        return frame

    def send_asdu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.state != ClientState.RUNNING:
            raise RuntimeError("Client stack is not running")
        frame = {
            "type": "I",
            "send_seq": self.send_sequence,
            "recv_seq": self.recv_sequence,
            "payload": payload,
            "timestamp": time.time(),
            "routing": self._routing_context(),
            "originator_address": self.originator_address,
        }
        self.send_sequence = (self.send_sequence + 1) % 32768
        self.sent_frames += 1
        self._maybe_send_s_frame()
        return frame

    def _maybe_send_s_frame(self) -> None:
        if self.sent_frames % self.k_window == 0:
            self._send_s_frame()

    def receive_frame(self, frame_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.received_frames += 1
        self.recv_sequence = (self.recv_sequence + 1) % 32768
        response = {
            "frame_type": frame_type,
            "payload": payload,
            "timestamp": time.time(),
            "routing": {
                "source": {
                    "ip": self.partner_ip,
                    "station_address": self.partner_station_address,
                },
                "destination": {
                    "ip": self.listen_ip,
                    "port": self.listen_port,
                },
            },
        }
        if frame_type == "I" and self.received_frames % self.w_window == 0:
            response["ack"] = self._send_s_frame()
        return response

    def simulate_network_packet(self) -> Dict[str, Any]:
        if self.state != ClientState.RUNNING:
            raise RuntimeError("Client stack is not running")
        payload = {"value": random.randint(0, 100)}
        return self.receive_frame("I", payload)

    def status(self) -> Dict[str, Any]:
        communication = self._routing_context()
        communication["originator_address"] = self.originator_address
        return {
            "state": self.state.value,
            "timers": {
                "t1": self.timers.t1,
                "t2": self.timers.t2,
                "t3": self.timers.t3,
            },
            "send_sequence": self.send_sequence,
            "recv_sequence": self.recv_sequence,
            "sent_frames": self.sent_frames,
            "received_frames": self.received_frames,
            "k_window": self.k_window,
            "w_window": self.w_window,
            "connection": {
                "attempts": self.connection_attempts,
                "last_established": self.last_connection_established,
            },
            "communication": communication,
        }

    def _routing_context(self) -> Dict[str, Any]:
        return {
            "destination": {
                "ip": self.partner_ip,
                "station_address": self.partner_station_address,
            },
            "source": {
                "ip": self.listen_ip,
                "port": self.listen_port,
            },
        }

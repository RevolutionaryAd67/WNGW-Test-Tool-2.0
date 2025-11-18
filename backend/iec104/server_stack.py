from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from backend.iec104.connection_profiles import ServerConnectionProfile

class ServerState(str, Enum):
    OFFLINE = "offline"
    LISTENING = "listening"
    LINK_ESTABLISHED = "link_established"
    ACTIVE = "active"


@dataclass
class ServerTimers:
    t1: float = 20.0
    t2: float = 12.0
    t3: float = 25.0
    last_poll: float = field(default_factory=time.time)

    def reset(self) -> None:
        self.last_poll = time.time()


class IEC104ServerStack:
    """Standalone IEC-104 slave stack."""

    def __init__(self) -> None:
        self.state = ServerState.OFFLINE
        self.timers = ServerTimers()
        self.send_sequence = 0
        self.recv_sequence = 0
        self.k_window = 8
        self.w_window = 6
        self.pending_events: Dict[str, Any] = {}
        self.sent_frames = 0
        self.received_frames = 0
        self.partner_ip = ""
        self.partner_station_address = ""
        self.listen_ip = ""
        self.listen_port: Optional[int] = None
        self.station_address = ""
        self.originator_address = ""
        self._connection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.connection_attempts = 0
        self.last_client_request: Optional[float] = None

    def apply_connection_profile(self, profile: ServerConnectionProfile) -> None:
        self.partner_ip = profile.partner_ip
        self.partner_station_address = profile.partner_station_address
        self.listen_ip = profile.listen_ip
        self.listen_port = profile.listen_port
        self.station_address = profile.station_address
        self.originator_address = profile.originator_address

    def start(self) -> Dict[str, Any]:
        if self.state != ServerState.OFFLINE:
            return self.status()
        self._stop_event.clear()
        self.state = ServerState.LISTENING
        self.timers.reset()
        self._connection_thread = threading.Thread(
            target=self._listener_worker, name="iec104-server", daemon=True
        )
        self._connection_thread.start()
        self._accept_connection()
        return self.status()

    def _listener_worker(self) -> None:
        while not self._stop_event.is_set():
            if self.state == ServerState.ACTIVE:
                self._await_partner_poll()
            self._stop_event.wait(1.0)

    def _accept_connection(self) -> None:
        self.connection_attempts += 1
        time.sleep(0.01)
        self.state = ServerState.LINK_ESTABLISHED
        self._send_u_frame("STARTDT_CON")
        self.state = ServerState.ACTIVE
        self.last_client_request = time.time()

    def _await_partner_poll(self) -> None:
        if time.time() - self.timers.last_poll >= self.timers.t3:
            self._send_u_frame("TESTFR_CON")
        self.timers.reset()

    def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        if self._connection_thread and self._connection_thread.is_alive():
            self._connection_thread.join(timeout=1.0)
        self._connection_thread = None
        self.state = ServerState.OFFLINE
        self.send_sequence = 0
        self.recv_sequence = 0
        self.pending_events.clear()
        self.sent_frames = 0
        self.received_frames = 0
        return self.status()

    def reset(self) -> Dict[str, Any]:
        self.timers.reset()
        self.pending_events.clear()
        return self.status()

    def _send_u_frame(self, command: str) -> Dict[str, Any]:
        frame = {"type": "U", "command": command, "timestamp": time.time()}
        self.sent_frames += 1
        return frame

    def send_asdu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.state != ServerState.ACTIVE:
            raise RuntimeError("Server stack is not active")
        frame = {
            "type": "I",
            "send_seq": self.send_sequence,
            "recv_seq": self.recv_sequence,
            "payload": payload,
            "timestamp": time.time(),
            "cause": "spontaneous",
            "routing": self._routing_context(),
            "station_address": self.station_address,
            "originator_address": self.originator_address,
        }
        self.send_sequence = (self.send_sequence + 1) % 32768
        self.sent_frames += 1
        return frame

    def receive_frame(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        if self.state != ServerState.ACTIVE:
            raise RuntimeError("Server stack is not active")
        self.received_frames += 1
        self.recv_sequence = (self.recv_sequence + 1) % 32768
        response = {
            "type": "S",
            "ack": self.recv_sequence,
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
        if self.received_frames % self.w_window == 0:
            response["u_frame"] = self._send_u_frame("TESTFR_CON")
        return response

    def simulate_measurement(self) -> Dict[str, Any]:
        if self.state != ServerState.ACTIVE:
            raise RuntimeError("Server stack is not active")
        payload = {"measurement": random.random(), "quality": "good"}
        frame = self.send_asdu(payload)
        self.pending_events[str(time.time())] = frame
        return frame

    def status(self) -> Dict[str, Any]:
        communication = self._routing_context()
        communication["station_address"] = self.station_address
        communication["originator_address"] = self.originator_address
        return {
            "state": self.state.value,
            "timers": {"t1": self.timers.t1, "t2": self.timers.t2, "t3": self.timers.t3},
            "send_sequence": self.send_sequence,
            "recv_sequence": self.recv_sequence,
            "sent_frames": self.sent_frames,
            "received_frames": self.received_frames,
            "k_window": self.k_window,
            "w_window": self.w_window,
            "pending_events": len(self.pending_events),
            "connection": {
                "attempts": self.connection_attempts,
                "last_partner_request": self.last_client_request,
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

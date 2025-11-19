#   IEC-104-Kommunikationsprozesse
#
#   Das Skript übernimmt 2 Aufgaben:
#       1. Client: Starten, Verbindungen aufbauen, Telegrammen bestätigen, Keep-Alive
#       2. Server: Starten, auf Verbindungen warten, eingehende Telegramme beantworten, auf GA reagieren

from __future__ import annotations

import select
import socket
import time
from typing import Dict, Optional

from multiprocessing.synchronize import Event as MpEvent

from .config import ClientSettings, ServerSettings, load_client_settings, load_server_settings
from .iec104.protocol import (
    COT_LABELS,
    FrameParser,
    build_i_frame,
    build_s_frame,
    build_u_frame,
    decode_frame,
)


# Wartezeit zwischen neuen Verbindungsversuchen
RETRY_DELAY = 5.0
# Intervall für Keep-Alive-U-Frames (in Sekunden)
KEEPALIVE_INTERVAL = 15.0


# Schreibt ein Ereignis in die Queue, die vom Hauptprozess ausgewertet wird
def _publish_event(queue, event_type: str, payload: Dict) -> None:
    queue.put({"type": event_type, "payload": payload})

# Gemeinsame Hilfsfunktion für Client- und Serverprozesse
class _BaseEndpoint:
    def __init__(
        self,
        side: str,
        queue,
        local_ip: str,
        local_port: int,
        remote_ip: str,
        remote_port: int,
        stop_event: MpEvent,
    ) -> None:
        self.side = side
        self.queue = queue
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.stop_event = stop_event
        self._sequence = 0
        self._recv_sequence = 0
        self._last_event_ts = time.time()
        self._event_index = 0

    # gibt die nächste Sendesequenznummer zurück
    def next_sequence(self) -> int:
        value = self._sequence
        self._sequence += 1
        return value

    # Aktualisiert die erwartetet Empfangssequenznummer
    def update_recv_sequence(self, seq: int) -> None:
        self._recv_sequence = seq

    # Erweitert Ereignisse um Metadaten und publiziert sie
    def _publish(self, payload: Dict) -> None:
        timestamp = time.time()
        delta = max(0.0, timestamp - self._last_event_ts)
        self._last_event_ts = timestamp
        self._event_index += 1
        event = {
            "side": self.side,
            "sequence": self._event_index,
            "timestamp": timestamp,
            "delta": delta,
            "local_endpoint": f"{self.local_ip}:{self.local_port}",
            "remote_endpoint": f"{self.remote_ip}:{self.remote_port}",
        }
        event.update(payload)
        _publish_event(self.queue, "telegram", event)

    # Meldetet Verbindungsstatusänderungen
    def publish_connection_status(self, connected: bool) -> None:
        _publish_event(
            self.queue,
            "status",
            {
                "side": self.side,
                "connected": bool(connected),
                "local_ip": self.local_ip,
                "remote_ip": self.remote_ip,
                "local_endpoint": f"{self.local_ip}:{self.local_port}",
                "remote_endpoint": f"{self.remote_ip}:{self.remote_port}",
            },
        )

    # Erzeugt ein protokolliertes TCP-Ereignis
    def publish_tcp(self, label: str, direction: str) -> None:
        self._publish(
            {
                "frame_family": "TCP",
                "label": label,
                "direction": direction,
            }
        )

    # Publiziert ein dekodiertes IEC-104-Telegramm
    def publish_frame(self, telegram, direction: str) -> None:
        payload = {
            "frame_family": telegram.frame_family,
            "label": telegram.label,
            "direction": direction,
        }
        if telegram.type_id is not None:
            payload["type_id"] = telegram.type_id
        if telegram.cause is not None:
            payload["cause"] = telegram.cause
            payload["originator"] = telegram.originator
        if telegram.station is not None:
            payload["station"] = telegram.station
        if telegram.ioa is not None:
            payload["ioa"] = telegram.ioa
        self._publish(payload)

    def publish_custom(
        self,
        frame_family: str,
        label: str,
        direction: str,
        type_id: Optional[int] = None,
        cause: Optional[int] = None,
        originator: Optional[int] = None,
        station: Optional[int] = None,
        ioa: Optional[int] = None,
    ) -> None:
        payload = {
            "frame_family": frame_family,
            "label": label,
            "direction": direction,
        }
        if type_id is not None:
            payload["type_id"] = type_id
        if cause is not None:
            payload["cause"] = cause
        if originator is not None:
            payload["originator"] = originator
        if station is not None:
            payload["station"] = station
        if ioa is not None:
            payload["ioa"] = ioa
        self._publish(payload)


# Initialisiert Client-spezifische Ressourcen
class IEC104ClientProcess(_BaseEndpoint):
    def __init__(self, queue, settings: ClientSettings, stop_event: MpEvent) -> None:
        super().__init__(
            side="client",
            queue=queue,
            local_ip=settings.local_ip,
            local_port=settings.local_port,
            remote_ip=settings.remote_ip,
            remote_port=settings.remote_port,
            stop_event=stop_event,
        )
        self.settings = settings
        self._parser = FrameParser()
        self._sock: Optional[socket.socket] = None
        self._last_keepalive = 0.0

    # Hauptschleife: Versucht Verbindungen aufzubauen und verarbeitet sie
    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._connect()
                self._loop()
            except ConnectionError as exc:
                self.publish_tcp(f"Verbindung getrennt: {exc}", "incoming")
                self._close_socket()
                self.publish_connection_status(False)
                if not self.stop_event.is_set():
                    time.sleep(RETRY_DELAY)
            except Exception as exc:
                self.publish_tcp(f"Unerwarteter Fehler: {exc}", "incoming")
                self._close_socket()
                self.publish_connection_status(False)
                if not self.stop_event.is_set():
                    time.sleep(RETRY_DELAY)

    # Stellt die TCP-verbindung her und sendet STARTDT
    def _connect(self) -> None:
        self._close_socket()
        self._recv_sequence = 0
        self._parser = FrameParser()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.local_ip, self.local_port))
        sock.connect((self.remote_ip, self.remote_port))
        sock.settimeout(None)
        self._sock = sock
        self.publish_tcp("SYN", "outgoing")
        self.publish_tcp("SYN ACK", "incoming")
        self.publish_tcp("ACK", "outgoing")
        self._send_u_frame(0x07, "STARTDT ACT")
        self.publish_connection_status(True)

    # Schließt die Socket-Verbindung sicher 
    def _close_socket(self, publish_reset: bool = False) -> None:
        had_socket = self._sock is not None
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if publish_reset and had_socket:
            self.publish_tcp("RST ACK", "outgoing")

    # Sendet rohen Payload über den aktiven Socket
    def _send(self, payload: bytes) -> None:
        if not self._sock:
            raise RuntimeError("Socket not connected")
        self._sock.sendall(payload)

    # Sendet einen U-Frame und protokolliert ihn
    def _send_u_frame(self, command: int, label: str) -> None:
        payload = build_u_frame(command)
        self._send(payload)
        self.publish_custom("U", label, "outgoing")

    # Sendet einen S-Frame als Quittung
    def _send_s_frame(self) -> None:
        payload = build_s_frame(self._recv_sequence)
        self._send(payload)
        self.publish_custom("S", "S-FRAME", "outgoing")

    # Verarbeitet eingehende Daten und reagiert auf Keep-Alive-Zeitüberschreitungen
    def _loop(self) -> None:
        if not self._sock:
            return
        self._last_keepalive = time.time()
        while not self.stop_event.is_set():
            ready, _, _ = select.select([self._sock], [], [], 1.0)
            if ready:
                try:
                    data = self._sock.recv(4096)
                except ConnectionResetError:
                    self.publish_tcp("RST ACK", "incoming")
                    raise ConnectionError("Kommunikationspartner hat zurückgesetzt")
                if not data:
                    self.publish_tcp("RST ACK", "incoming")
                    raise ConnectionError("Kommunikationspartner hat getrennt")
                for frame in self._parser.feed(data):
                    telegram = decode_frame(frame)
                    self.publish_frame(telegram, "incoming")
                    if telegram.frame_family == "I":
                        self._recv_sequence += 1
                        self._send_s_frame()
            now = time.time()
            if now - self._last_keepalive >= KEEPALIVE_INTERVAL:
                self._send_u_frame(0x43, "TESTFR ACT")
                self._last_keepalive = now
        # stop requested
        self._close_socket(publish_reset=True)
        self.publish_connection_status(False)


# Serverprozess, der IEC-104-Verbindungen entgegen nimmt
class IEC104ServerProcess(_BaseEndpoint):
    def __init__(self, queue, settings: ServerSettings, stop_event: MpEvent) -> None:
        super().__init__(
            side="server",
            queue=queue,
            local_ip=settings.local_ip,
            local_port=settings.local_port,
            remote_ip=settings.remote_ip,
            remote_port=settings.remote_port,
            stop_event=stop_event,
        )
        self.settings = settings
        self._parser = FrameParser()
        self._send_sequence = 0

    # Startet einen TCP-Listener und bearbeitet eingehende Verbindungen
    def run(self) -> None:
        while not self.stop_event.is_set():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.local_ip, self.local_port))
                server.listen(1)
                server.settimeout(1.0)
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(None)
                    self._handle_connection(conn, addr)
                    if self.stop_event.is_set():
                        break

    # Verarbeitet eine einzelne Client-Verbindung
    def _handle_connection(self, conn: socket.socket, addr) -> None:
        self._recv_sequence = 0
        self._send_sequence = 0
        self._parser = FrameParser()
        self.publish_tcp("SYN", "incoming")
        self.publish_tcp("SYN ACK", "outgoing")
        self.publish_tcp("ACK", "incoming")
        self.publish_connection_status(True)
        while not self.stop_event.is_set():
            ready, _, _ = select.select([conn], [], [], 1.0)
            if ready:
                try:
                    data = conn.recv(4096)
                except ConnectionResetError:
                    self.publish_tcp("RST ACK", "incoming")
                    break
                if not data:
                    self.publish_tcp("RST ACK", "incoming")
                    break
                for frame in self._parser.feed(data):
                    telegram = decode_frame(frame)
                    self.publish_frame(telegram, "incoming")
                    if telegram.frame_family == "U":
                        if telegram.label == "STARTDT ACT":
                            self._send_u_frame(conn, 0x0B, "STARTDT CON")
                        if telegram.label == "TESTFR ACT":
                            self._send_u_frame(conn, 0x83, "TESTFR CON")
                    if telegram.frame_family == "I":
                        self._recv_sequence += 1
                        if (
                            telegram.type_id == 100
                            and telegram.cause == 6
                        ):
                            self._send_general_interrogation_response(conn)
                        self._send_s_frame(conn)
        if self.stop_event.is_set():
            self.publish_tcp("RST ACK", "outgoing")
        self.publish_connection_status(False)

    # Hilfsfunktion zum Versenden eines U-Frames
    def _send_u_frame(self, conn: socket.socket, command: int, label: str) -> None:
        payload = build_u_frame(command)
        conn.sendall(payload)
        self.publish_custom("U", label, "outgoing")

    # Hilfsfunktion zum Versenden eines S-Frames
    def _send_s_frame(self, conn: socket.socket) -> None:
        payload = build_s_frame(self._recv_sequence)
        conn.sendall(payload)
        self.publish_custom("S", "S-FRAME", "outgoing")

    # Antwortet auf eine Generalabfrage mit GENERALABFRAGE CON und END
    def _send_general_interrogation_response(self, conn: socket.socket) -> None:
        for cot in (7, 10):
            frame = build_i_frame(
                send_sequence=self._send_sequence,
                recv_sequence=self._recv_sequence,
                type_id=100,
                cause=cot,
                originator=0,
                common_address=self.settings.common_address,
                ioa=0,
                information=bytes([20]),
            )
            conn.sendall(frame)
            label = COT_LABELS.get((100, cot), "GENERALABFRAGE")
            self.publish_custom(
                "I",
                label,
                "outgoing",
                type_id=100,
                cause=cot,
                originator=0,
                station=self.settings.common_address,
                ioa=0,
            )
            self._send_sequence += 1


# Startet den Client
def run_client_process(queue, stop_event: MpEvent) -> None:
    settings = load_client_settings()
    IEC104ClientProcess(queue, settings, stop_event).run()


# Startet den Server
def run_server_process(queue, stop_event: MpEvent) -> None:
    settings = load_server_settings()
    IEC104ServerProcess(queue, settings, stop_event).run()

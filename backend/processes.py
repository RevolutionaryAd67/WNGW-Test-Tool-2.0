#   IEC-104-Kommunikationsprozesse
#
#   Aufgaben des Skripts:
#       1. Client: Starten, Verbindungen aufbauen, Telegrammen bestätigen, Keep-Alive
#       2. Server: Starten, auf Verbindungen warten, eingehende Telegramme beantworten, auf GA reagieren

from __future__ import annotations

import re
import select
import socket
import struct
import time
from queue import Empty
from typing import Dict, List, Optional, Tuple

from multiprocessing.synchronize import Event as MpEvent

from .config import (
    DATA_DIR,
    ClientSettings,
    ServerSettings,
    load_client_settings,
    load_server_settings,
)
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


# Anzahl der Bytes pro Informationselement (ohne IOA) je Typkennung für Telegramme
# mit einfacher Informations-Satz-Struktur (inkl. Zeitstempel/Qualifier, falls
# vorhanden). Für komplexere Typen wird auf Rohbytes zurückgegriffen.
TYPE_INFORMATION_LENGTHS: Dict[int, int] = {
    1: 1,    # M_SP_NA_1: 1x SIQ
    3: 1,    # M_DP_NA_1: 1x DIQ
    5: 2,    # M_ST_NA_1: 1x Byte + QDS
    7: 5,    # M_BO_NA_1: 4x Byte + QDS
    9: 3,    # M_ME_NA_1: 2x Byte + QDS
    11: 3,   # M_ME_NB_1: 2x Byte + QDS
    13: 5,   # M_ME_NC_1: 4x Float + QDS
    15: 5,   # M_IT_NA_1: 4x Byte + QDS
    30: 8,   # M_SP_TB_1: 1x SIQ + CP56Time2a
    31: 8,   # M_DP_TB_1: 1x DIQ + CP56Time2a
    36: 12,  # M_ME_TF_1: 4x Float + QDS + CP56Time2a
    58: 8,   # Doppelbefehl mit Zeitmarke (DCO + CP56Time2a)
    59: 1,   # C_RP_NA_1: 1x QRP
    63: 12,  # C_SE_TC_1: 4x Float + QOS + CP56Time2a
    70: 1,   # M_EI_NA_1: 1x COI
    100: 1,  # C_IC_NA_1: 1x QOI
    103: 7,  # C_CS_NA_1 (Alternative): CP56Time2a
}

# Anzahl der Bytes, die den eigentlichen Wert (ohne Qualifier/Zeitsstempel)
# eines Informationselements abbilden.
TYPE_VALUE_FIELD_LENGTHS: Dict[int, int] = {
    1: 1,    # SIQ (Statusbits eingeschlossen)
    3: 1,    # DIQ (Statusbits eingeschlossen)
    5: 1,    # Stellungswert ohne QDS
    7: 4,    # 32-Bit-Bitstring ohne QDS
    9: 2,    # 16-Bit-Messwert ohne QDS
    11: 2,   # 16-Bit-Messwert ohne QDS
    13: 4,   # Float ohne QDS
    15: 4,   # Zählerwert ohne QDS
    30: 1,   # SIQ ohne Zeitstempel
    31: 1,   # DIQ ohne Zeitstempel
    36: 4,   # Float ohne QDS/Zeitsstempel
    58: 1,   # DCO (S/E + QU + DCS)
    59: 1,   # QRP
    63: 5,   # 4x Float + QOS
    70: 1,   # COI
    100: 1,  # QOI
    103: 7,  # Zeitfeld
}

# Typkennungen, die ein CP56Time2a-Zeitfeld enthalten
TIMESTAMP_TYPES = {30, 31, 36, 58, 63, 103}
TIME_ONLY_TYPES = {103}

# Name und Byte-Offset des Qualifier-Feldes je Typkennung (sofern vorhanden)
QUALIFIER_FIELD_SPECS: Dict[int, Tuple[str, int]] = {
    1: ("SIQ", 0),
    3: ("DIQ", 0),
    5: ("QDS", 1),
    7: ("QDS", 4),
    9: ("QDS", 2),
    11: ("QDS", 2),
    13: ("QDS", 4),
    15: ("QDS", 4),
    30: ("SIQ", 0),
    31: ("DIQ", 0),
    36: ("QDS", 4),
    58: ("DCO", 0),
    59: ("QRP", 0),
    63: ("QOS", 4),
    70: ("COI", 0),
    100: ("QOI", 0),
}


# Liest VSQ und gibt Objektanzahl sowie den Informationsbereich zurück
def _extract_information_bytes(payload: bytes) -> Tuple[int, bytes]:
    if len(payload) <= 9:
        return 0, b""
    vsq = payload[1]
    count = max(1, vsq & 0x7F)
    start = 9
    return count, payload[start:]


# Dekodiert ein einfaches Statusqualitätsbyte (SIQ) in einen Klartextwert
def _decode_siq(info_bytes: bytes) -> Optional[str]:
    if not info_bytes:
        return None
    siq = info_bytes[0]
    value = "Ein" if siq & 0x01 else "Aus"
    return value


# Dekodiert ein doppeltes Statusqualitätsbyte (DIQ) in einen Klartextwert
def _decode_diq(info_bytes: bytes) -> Optional[str]:
    if not info_bytes:
        return None
    diq = info_bytes[0] & 0x03
    state_labels = {0: "Unbestimmt", 1: "Aus", 2: "Ein", 3: "Unbestimmt"}
    label = state_labels.get(diq, "Unbekannt")
    return label


# Dekodiert eine Stellungsinformation mit Vorzeichen in einen Textwert
def _decode_step_position(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 1:
        return None
    value = struct.unpack("<b", bytes([info_bytes[0]]))[0]
    return str(value)


# Wandelt einen 32-Bit-Bitstring in eine formatierte Binärdarstellung um
def _decode_bitstring32(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 4:
        return None
    value = int.from_bytes(info_bytes[:4], "little", signed=False)
    return f"0b{value:032b}"


# Dekodiert einen 16-Bit-Ganzzahlwert aus dem Informationsbereich
def _decode_int16_value(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 2:
        return None
    value = int.from_bytes(info_bytes[:2], "little", signed=True)
    return str(value)


# Dekodiert einen Float-Wert aus dem Informationsbereich
def _decode_float_value(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 4:
        return None
    value = struct.unpack("<f", info_bytes[:4])[0]
    return str(value)


# Dekodiert einen 32-Bit-Ganzzahlwert aus dem Informationsbereich
def _decode_int32_value(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 4:
        return None
    value = int.from_bytes(info_bytes[:4], "little", signed=True)
    return str(value)


def _decode_double_command(info_bytes: bytes) -> Optional[str]:
    if len(info_bytes) < 1:
        return None
    dco = info_bytes[0]
    se_flag = (dco >> 7) & 0x01
    qu_value = (dco >> 2) & 0x1F
    dcs_value = dco & 0x03
    return f"S/E={se_flag}, QU={qu_value}, DCS={dcs_value}"


# Typkennungen und deren dazugehörige Decoder
TYPE_VALUE_DECODERS = {
    1: _decode_siq,
    3: _decode_diq,
    5: _decode_step_position,
    7: _decode_bitstring32,
    9: _decode_int16_value,
    11: _decode_int16_value,
    13: _decode_float_value,
    15: _decode_int32_value,
    30: _decode_siq,
    31: _decode_diq,
    36: _decode_float_value,
    58: _decode_double_command,
    63: _decode_float_value,
}


# Wählt den passenden Decoder für einen I-Frame und liefert den Nutzwert als Text
def _decode_information_value(type_id: Optional[int], payload: bytes) -> Optional[str]:
    """Dekodiert den Wert eines I-Frames entsprechend der Typkennung."""

    if type_id is None:
        return None
    count, information_bytes = _extract_information_bytes(payload)
    if not information_bytes:
        return None

    decoder = TYPE_VALUE_DECODERS.get(type_id)
    if decoder:
        value = decoder(information_bytes)
        if value is not None:
            return value

    length = TYPE_VALUE_FIELD_LENGTHS.get(type_id) or TYPE_INFORMATION_LENGTHS.get(type_id)
    if length and len(information_bytes) >= length:
        relevant = information_bytes[:length]
    else:
        relevant = information_bytes
    if not relevant:
        return None
    return " ".join(f"0x{byte:02X}" for byte in relevant)


# Extrahiert ein Qualifier-Feld anhand der Typkennung und liefert Label und Wert zurück
def _decode_qualifier_field(
    type_id: Optional[int], payload: bytes
) -> Optional[Dict[str, int]]:
    if type_id is None:
        return None

    spec = QUALIFIER_FIELD_SPECS.get(type_id)
    if not spec:
        return None

    _, information_bytes = _extract_information_bytes(payload)
    label, index = spec
    if not information_bytes or index >= len(information_bytes):
        return None

    return {"label": label, "value": information_bytes[index]}


# Wandelt einen beliebigen Wert sicher in einen Integer um oder liefert einen Standardwert
def _safe_int(value: object, default: int = 0) -> int:
    try:
        text = str(value).strip()
        if not text:
            return default
        return int(text, 0)
    except (TypeError, ValueError):
        return default


# Kodiert einen angegebenen Textwert passend zum Typ in Rohbytes der gewünschten Länge
def _encode_value_bytes(type_id: int, value_text: str, length: int) -> bytes:
    if length <= 0:
        return b""
    text = "" if value_text is None else str(value_text).strip()
    try:
        if type_id in (13, 36, 63):
            float_part = struct.pack("<f", float(text or 0))
            if length <= len(float_part):
                return float_part[:length]
            return float_part + b"\x00" * (length - len(float_part))
    except (TypeError, ValueError):
        pass
    try:
        number = int(text or 0, 0)
    except (TypeError, ValueError):
        number = 0
    signed_types = {5, 9, 11, 13, 15, 36}
    unsigned_types = {1, 3, 7, 30, 31}
    signed = type_id in signed_types and type_id not in unsigned_types
    raw = number.to_bytes(length, "little", signed=signed)
    if len(raw) < length:
        raw = raw + b"\x00" * (length - len(raw))
    return raw[:length]


# Kodiert einen CP56Time2a-Zeitstempel basierend auf der aktuellen Systemzeit
def _build_cp56time2a(timestamp: Optional[float] = None) -> bytes:
    ts = time.time() if timestamp is None else timestamp
    millis_since_minute = int(round((ts * 1000))) % 60000
    seconds_bytes = millis_since_minute.to_bytes(2, "little", signed=False)
    tm = time.localtime(ts)
    minute = tm.tm_min & 0x3F
    hour = tm.tm_hour & 0x1F
    weekday = ((tm.tm_wday + 1) & 0x07) << 5
    day = (tm.tm_mday & 0x1F) | weekday
    month = tm.tm_mon & 0x0F
    year = (tm.tm_year - 2000) & 0x7F
    return seconds_bytes + bytes([minute, hour, day, month, year])


# Baut den Informationsbereich eines I-Frames anhand des Typs und eines Textwerts
_QUALIFIER_PATTERN = re.compile(r"^[01]{8}$")


def _parse_qualifier_byte(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not _QUALIFIER_PATTERN.fullmatch(text):
        return None
    return int(text, 2) & 0xFF


def _build_type_58_information(value_text: str, qualifier_text: Optional[str]) -> bytes:
    dcs_value = _safe_int(value_text, default=0) & 0x03
    se_flag = 0
    qu_value = 0

    if qualifier_text:
        text = str(qualifier_text).strip()
        pair_match = re.match(r"^([01])\s*,\s*(\d+)$", text)
        if pair_match:
            se_flag = _safe_int(pair_match.group(1), default=0) & 0x01
            qu_value = _safe_int(pair_match.group(2), default=0)
        else:
            for part in re.split(r"[;,\s]+", text):
                if not part:
                    continue
                if "=" in part:
                    key, val = part.split("=", 1)
                    lowered = key.strip().lower()
                    if lowered in {"se", "s/e", "select", "anwahl", "ausfuehrung"}:
                        se_flag = _safe_int(val, default=0) & 0x01
                        continue
                    if lowered in {"qu", "qualifier"}:
                        qu_value = _safe_int(val, default=0)
                        continue
                if qu_value == 0:
                    qu_value = _safe_int(part, default=0)

    qu_value = max(0, min(qu_value, 0x1F))
    dco = (se_flag << 7) | ((qu_value & 0x1F) << 2) | dcs_value
    return bytes([dco]) + _build_cp56time2a()


def _build_information_bytes(type_id: int, value_text: str, qualifier_text: Optional[str] = None) -> bytes:
    if type_id == 58:
        return _build_type_58_information(value_text, qualifier_text)
    total_length = TYPE_INFORMATION_LENGTHS.get(type_id)
    value_length = TYPE_VALUE_FIELD_LENGTHS.get(type_id, total_length or 0)
    if type_id in TIME_ONLY_TYPES:
        value_length = 0
    encoded_value = (
        _encode_value_bytes(type_id, value_text, value_length) if value_length else b""
    )
    if total_length is None:
        return encoded_value
    payload = bytearray(total_length)
    if encoded_value:
        payload[: min(len(encoded_value), total_length)] = encoded_value[:total_length]
    if type_id in TIMESTAMP_TYPES:
        cp56time = _build_cp56time2a()
        start = max(0, total_length - len(cp56time))
        end = start + min(len(cp56time), total_length - start)
        payload[start:end] = cp56time[: end - start]
    qualifier_value = _parse_qualifier_byte(qualifier_text)
    if qualifier_value is not None:
        qualifier_field = QUALIFIER_FIELD_SPECS.get(type_id)
        if qualifier_field:
            _, offset = qualifier_field
            if 0 <= offset < total_length:
                payload[offset] = qualifier_value
    return bytes(payload)


# Schreibt ein Ereignis in die Queue, die vom Hauptprozess ausgewertet wird
def _publish_event(queue, event_type: str, payload: Dict) -> None:
    queue.put({"type": event_type, "payload": payload})

# Gemeinsame Hilfsfunktion für Client- und Serverprozesse
class _BaseEndpoint:
    def __init__(
        self,
        side: str,
        queue,
        command_queue,
        local_ip: str,
        local_port: int,
        remote_ip: str,
        remote_port: int,
        stop_event: MpEvent,
    ) -> None:
        self.side = side
        self.queue = queue
        self.command_queue = command_queue
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.stop_event = stop_event
        self._sequence = 0
        self._recv_sequence = 0
        self._last_event_ts = time.time()
        self._event_index = 0
        self._pending_signals: List[Dict[str, str]] = []
        self._test_active = False

    # Gibt die nächste Sendesequenznummer zurück
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
        if telegram.frame_family == "I" and telegram.payload:
            value = _decode_information_value(telegram.type_id, telegram.payload)
            if value is not None:
                payload["value"] = value
            qualifier = _decode_qualifier_field(telegram.type_id, telegram.payload)
            if qualifier is not None:
                payload["qualifier"] = qualifier
        self._publish(payload)

    # Publiziert ein frei zusammenstellbares Telegramm-Ereignis
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
        value: Optional[str] = None,
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
        if value is not None:
            payload["value"] = value
        self._publish(payload)

    def _process_commands(self) -> None:
        while True:
            try:
                command = self.command_queue.get_nowait()
            except Empty:
                break
            if not isinstance(command, dict):
                continue
            if command.get("action") == "send_signal":
                row = command.get("row")
                if isinstance(row, dict):
                    self._pending_signals.append(row)
            if command.get("action") == "set_test_active":
                self._test_active = bool(command.get("active"))

    def _flush_pending(self, sender) -> None:
        while self._pending_signals and not self.stop_event.is_set():
            row = self._pending_signals.pop(0)
            sender(row)
            time.sleep(0.02)


# Initialisiert Client-spezifische Ressourcen
class IEC104ClientProcess(_BaseEndpoint):
    def __init__(
        self, queue, command_queue, settings: ClientSettings, stop_event: MpEvent
    ) -> None:
        super().__init__(
            side="client",
            queue=queue,
            command_queue=command_queue,
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
            self._process_commands()
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
        self._sequence = 0
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
            self._process_commands()
            self._flush_pending(self._send_signal_from_row)
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

    def _build_signal_frame(self, row: Dict[str, str]) -> Optional[Dict[str, object]]:
        type_id = _safe_int(row.get("IEC104- Typ"))
        if type_id <= 0:
            return None
        cause = _safe_int(row.get("Übertragungsursache"), default=20)
        originator = _safe_int(row.get("Herkunftsadresse"), default=self.settings.originator_address)
        ioa1 = _safe_int(row.get("IOA 1")) & 0xFF
        ioa2 = _safe_int(row.get("IOA 2")) & 0xFF
        ioa3 = _safe_int(row.get("IOA 3")) & 0xFF
        ioa = ioa1 | (ioa2 << 8) | (ioa3 << 16)
        value_text = str(row.get("Wert", ""))
        if type_id == 100 and cause == 6:
            information = bytes([20])
            value_text = "20" if not value_text.strip() else value_text
        else:
            information = _build_information_bytes(
                type_id, value_text, row.get("Qualifier")
            )
        frame = build_i_frame(
            send_sequence=self._sequence,
            recv_sequence=self._recv_sequence,
            type_id=type_id,
            cause=cause,
            originator=originator,
            common_address=self.settings.remote_asdu,
            ioa=ioa,
            information=information,
        )
        label = (
            COT_LABELS.get((type_id, cause))
            or row.get("Datenpunkt / Meldetext")
            or COT_LABELS.get((100, cause), "GENERALABFRAGE")
        )
        return {
            "frame": frame,
            "label": label,
            "type_id": type_id,
            "cause": cause,
            "originator": originator,
            "ioa": ioa,
            "value": value_text,
        }

    def _send_signal_from_row(self, row: Dict[str, str]) -> None:
        if not self._sock:
            self._pending_signals.insert(0, row)
            return
        telegram = self._build_signal_frame(row)
        if not telegram:
            return
        try:
            self._send(telegram["frame"])
        except Exception as exc:
            self._pending_signals.insert(0, row)
            self.publish_tcp(f"Senden fehlgeschlagen: {exc}", "outgoing")
            return
        self.publish_custom(
            "I",
            telegram["label"],
            "outgoing",
            type_id=telegram.get("type_id"),
            cause=telegram.get("cause"),
            originator=telegram.get("originator"),
            station=self.settings.remote_asdu,
            ioa=telegram.get("ioa"),
            value=telegram.get("value"),
        )
        self._sequence += 1


# Serverprozess, der IEC-104-Verbindungen entgegen nimmt
class IEC104ServerProcess(_BaseEndpoint):
    def __init__(
        self, queue, command_queue, settings: ServerSettings, stop_event: MpEvent
    ) -> None:
        super().__init__(
            side="server",
            queue=queue,
            command_queue=command_queue,
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
                    self._process_commands()
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
            self._process_commands()
            self._flush_pending(lambda row: self._send_signal_from_row(conn, row))
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
                            and not self._test_active
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

    # Sendet eine Bestätigung für eine Generalabfrage mit dem gewünschten COT
    def _send_general_confirmation(self, conn: socket.socket, cot: int) -> None:
        frame = build_i_frame(
            send_sequence=self._send_sequence,
            recv_sequence=self._recv_sequence,
            type_id=100,
            cause=cot,
            originator=self.settings.originator_address,
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
            originator=self.settings.originator_address,
            station=self.settings.common_address,
            ioa=0,
        )
        self._send_sequence += 1

    # Baut ein I-Frame-Paket aus einer Signallistenzeile auf
    def _build_signal_frame(self, row: Dict[str, str]) -> Optional[Dict[str, object]]:
        type_id = _safe_int(row.get("IEC104- Typ"))
        if type_id <= 0:
            return None
        cause = _safe_int(row.get("Übertragungsursache"), default=20)
        originator = _safe_int(row.get("Herkunftsadresse"), default=self.settings.originator_address)
        ioa1 = _safe_int(row.get("IOA 1")) & 0xFF
        ioa2 = _safe_int(row.get("IOA 2")) & 0xFF
        ioa3 = _safe_int(row.get("IOA 3")) & 0xFF
        ioa = ioa1 | (ioa2 << 8) | (ioa3 << 16)
        information = _build_information_bytes(
            type_id, str(row.get("Wert", "")), row.get("Qualifier")
        )
        frame = build_i_frame(
            send_sequence=self._send_sequence,
            recv_sequence=self._recv_sequence,
            type_id=type_id,
            cause=cause,
            originator=originator,
            common_address=self.settings.common_address,
            ioa=ioa,
            information=information,
        )
        label = (
            COT_LABELS.get((type_id, cause))
            or row.get("Datenpunkt / Meldetext")
            or COT_LABELS.get((100, cause), "GENERALABFRAGE")
        )
        return {
            "frame": frame,
            "label": label,
            "type_id": type_id,
            "cause": cause,
            "originator": originator,
            "ioa": ioa,
            "value": str(row.get("Wert", "")),
        }

    # Antwortet auf eine Generalabfrage ausschließlich mit GENERALABFRAGE CON und END
    def _send_general_interrogation_response(self, conn: socket.socket) -> None:
        self._send_general_confirmation(conn, 7)
        self._send_general_confirmation(conn, 10)

    def _send_signal_from_row(self, conn: socket.socket, row: Dict[str, str]) -> None:
        telegram = self._build_signal_frame(row)
        if not telegram:
            return
        try:
            conn.sendall(telegram["frame"])
        except Exception as exc:
            self._pending_signals.insert(0, row)
            self.publish_tcp(f"Senden fehlgeschlagen: {exc}", "outgoing")
            return
        self.publish_custom(
            "I",
            telegram["label"],
            "outgoing",
            type_id=telegram.get("type_id"),
            cause=telegram.get("cause"),
            originator=telegram.get("originator"),
            station=self.settings.common_address,
            ioa=telegram.get("ioa"),
            value=telegram.get("value"),
        )
        self._send_sequence += 1


# Startet den Client
def run_client_process(queue, stop_event: MpEvent, command_queue) -> None:
    settings = load_client_settings()
    IEC104ClientProcess(queue, command_queue, settings, stop_event).run()


# Startet den Server
def run_server_process(queue, stop_event: MpEvent, command_queue) -> None:
    settings = load_server_settings()
    IEC104ServerProcess(queue, command_queue, settings, stop_event).run()

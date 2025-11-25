#   Utilities zum Parsen, Dekodieren und Erzeugen von IEC-104-Frames
#
#   Aufgaben des Skripts:
#       1. Bytes aus Telegrammen erkennen
#       2. U-, S- und I-Frame bauen

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# Bekannte Kontrollbefehle von bestimmten U-Frames und deren Bezeichnis
U_FRAME_LABELS = {
    0x07: "STARTDT ACT",
    0x0B: "STARTDT CON",
    0x13: "STOPDT ACT",
    0x23: "STOPDT CON",
    0x43: "TESTFR ACT",
    0x83: "TESTFR CON",
}

# Bekannte Typkennungen für I-Frames
TYPE_LABELS = {
    70: "INITIALISIERUNGSENDE",
    100: "GENERALABFRAGE",
}

# Kombination aus Typ und COT zu menschenlesbaren labels
COT_LABELS = {
    (100, 6): "GENERALABFRAGE ACT",
    (100, 7): "GENERALABFRAGE CON",
    (100, 10): "GENERALABFRAGE END",
}


# Darstellung eines dekodierten Telegramms, wie es von decode_frame geliefert wird
@dataclass
class Telegram:
    frame_family: str
    label: str
    type_id: Optional[int]
    cause: Optional[int]
    originator: Optional[int]
    station: Optional[int]
    ioa: Optional[int]
    payload: bytes
    direction: str


# Frame-Parser für Byte-Ströme
class FrameParser:

    # Eingehende Daten werden gepuffert
    def __init__(self) -> None:
        self._buffer = bytearray()

    # Füttert neue Bytes und liefert alle vollständig erkannten Frames
    def feed(self, data: bytes) -> List[bytes]:
        frames: List[bytes] = []
        self._buffer.extend(data)
        while True:
            if len(self._buffer) < 2:
                break
            if self._buffer[0] != 0x68: # Ungültiges Startbyte: so lange verwerfen bis wieder 0x68 auftaucht
                self._buffer.pop(0)
                continue
            length = self._buffer[1]
            needed = length + 2
            if len(self._buffer) < needed:
                break
            frame = bytes(self._buffer[:needed])
            del self._buffer[:needed]
            frames.append(frame)
        return frames


# Hilfsfunktion, um Sende-/Emfpangszähler aus Control-Feld zu lesen
def _extract_sequences(frame: bytes) -> Dict[str, int]:
    if len(frame) < 6:
        return {"send": 0, "recv": 0}
    send = ((frame[3] << 8) | frame[2]) >> 1
    recv = ((frame[5] << 8) | frame[4]) >> 1
    return {"send": send, "recv": recv}


# Dekodiert ein Frame-Bytearray in ein Telegramm
# Es werden anhand des ersten Kontrollbytes die drei Frametypen (I,S,U) unterschieden und die vorhandenen Feld jeweils bestmöglich extrahiert
def decode_frame(frame: bytes) -> Telegram:
    control = frame[2:6]
    payload = frame[6:]
    ctrl1 = control[0]
    if ctrl1 & 0x01 == 0:
        type_id = payload[0] if payload else None
        cause = payload[2] if len(payload) >= 4 else None
        originator = payload[3] if len(payload) >= 4 else None
        station = payload[4] | (payload[5] << 8) if len(payload) >= 6 else None
        ioa = payload[6] | (payload[7] << 8) | (payload[8] << 16) if len(payload) >= 9 else None
        type_label = TYPE_LABELS.get(type_id)
        cause_label = COT_LABELS.get((type_id or 0, cause or 0))
        label = cause_label or type_label or "I-FRAME"
        return Telegram(
            frame_family="I",
            label=label,
            type_id=type_id,
            cause=cause,
            originator=originator,
            station=station,
            ioa=ioa,
            payload=payload,
            direction="incoming",
        )
    if ctrl1 & 0x03 == 0x03:
        label = U_FRAME_LABELS.get(ctrl1, "U-FRAME")
        return Telegram(
            frame_family="U",
            label=label,
            type_id=None,
            cause=None,
            originator=None,
            station=None,
            ioa=None,
            payload=payload,
            direction="incoming",
        )
    label = "S-FRAME"
    return Telegram(
        frame_family="S",
        label=label,
        type_id=None,
        cause=None,
        originator=None,
        station=None,
        ioa=None,
        payload=payload,
        direction="incoming",
    )


# Erzeugt U-Frame für den angegebenen Kommandocode
def build_u_frame(command: int) -> bytes:
    return bytes([0x68, 0x04, command, 0x00, 0x00, 0x00])


# Erzeugt S-Frame mit aktueller Empfangssequenz
def build_s_frame(recv_sequence: int) -> bytes:
    recv_field = recv_sequence << 1
    return bytes(
        [
            0x68,
            0x04,
            0x01,
            0x00,
            recv_field & 0xFF,
            (recv_field >> 8) & 0xFF,
        ]
    )


# Baut einen vollständigen I-Frame mitsamt ASDU-Daten
def build_i_frame(
    send_sequence: int,
    recv_sequence: int,
    type_id: int,
    cause: int,
    originator: int,
    common_address: int,
    ioa: int,
    information: bytes,
    vsq: int = 0x01,
) -> bytes:
    send_field = send_sequence << 1
    recv_field = recv_sequence << 1
    header = bytes(
        [
            0x68,
            len(information) + 13,
            send_field & 0xFF,
            (send_field >> 8) & 0xFF,
            recv_field & 0xFF,
            (recv_field >> 8) & 0xFF,
        ]
    )
    body = bytearray()
    body.append(type_id)
    body.append(vsq & 0xFF)  # VSQ
    body.append(cause & 0xFF)
    body.append(originator & 0xFF)
    body.append(common_address & 0xFF)
    body.append((common_address >> 8) & 0xFF)
    body.extend(ioa.to_bytes(3, "little"))
    body.extend(information)
    return header + bytes(body)

"""Hilfsfunktionen zum Ableiten von IEC-104-Telegrammen aus Signallisten.

Das Modul bildet die wichtigsten Felder eines I-Frames aus den Angaben in den
Signallisten ab. Die stationären Adressen werden aus den Einstellungsseiten
gelesen, sodass die erzeugten Telegramme den in der Oberfläche hinterlegten
Rollen (Client/Server) entsprechen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from .config import load_client_settings, load_server_settings
from .iec104.protocol import build_i_frame
from .processes import _build_information_bytes, _safe_int


@dataclass
class BuiltTelegram:
    """Repräsentation eines erzeugten I-Frames aus der Signalliste."""

    frame: bytes
    direction: str
    label: str
    type_id: int
    cause: int
    originator: int
    common_address: int
    ioa: int
    value: str


def _load_signalliste_rows(config_path: Path) -> List[Dict[str, str]]:
    """Extrahiert alle Signallistenzeilen aus einer Prüfkonfiguration."""

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    rows: List[Dict[str, str]] = []
    for teilpruefung in payload.get("teilpruefungen", []):
        signalliste = teilpruefung.get("signalliste", {}) or {}
        rows.extend(signalliste.get("rows", []) or [])
    return rows


def _direction_from_row(row: Dict[str, str]) -> str:
    """Leitet aus der NLS-Quelle/Senke ab, ob Client oder Server sendet."""

    sender_field = str(row.get("Quelle/Senke von der NLS betrachtet", "")).upper()
    return "client" if "Q" in sender_field else "server"


def _build_common_address(direction: str) -> int:
    """Ermittelt die CA entsprechend der Seite Client/Server."""

    client_settings = load_client_settings()
    server_settings = load_server_settings()
    if direction == "client":
        return client_settings.remote_asdu
    return server_settings.common_address


def _build_originator(direction: str, row: Dict[str, str]) -> int:
    """Bestimmt die Herkunftsadresse aus Zeile oder Einstellungen."""

    default = (
        load_client_settings().originator_address
        if direction == "client"
        else load_server_settings().originator_address
    )
    return _safe_int(row.get("Herkunftsadresse"), default=default)


def _build_ioa(row: Dict[str, str]) -> int:
    """Setzt IOA aus den drei Bytes der Signalliste zusammen."""

    ioa1 = _safe_int(row.get("IOA 1")) & 0xFF
    ioa2 = _safe_int(row.get("IOA 2")) & 0xFF
    ioa3 = _safe_int(row.get("IOA 3")) & 0xFF
    return ioa1 | (ioa2 << 8) | (ioa3 << 16)


def _build_label(row: Dict[str, str], cause: int, type_id: int) -> str:
    """Wählt eine menschenlesbare Beschreibung für das Telegramm."""

    text = row.get("Datenpunkt / Meldetext")
    if text:
        return str(text)
    if type_id == 100 and cause in (6, 7, 10):
        return "GENERALABFRAGE"
    return f"TYPE {type_id}"


def build_telegrams(
    config_path: Path,
    *,
    send_sequence_start: int = 0,
    recv_sequence_start: int = 0,
) -> Iterable[BuiltTelegram]:
    """Erzeugt I-Frames mit VSQ=0 auf Basis einer Signalliste.

    Die Funktion wertet die Prüfkonfigurations-Datei aus, leitet pro Zeile die
    Sende-Rolle ab und baut ein vollständiges IEC-104-I-Frame mit fester VSQ=0.
    Die Common Address (CA) wird
    * für Client-Telegramme aus der Seite "Client" (Feld "Gemeinsame Adresse der
      ASDU (CA)")
    * für Server-Telegramme aus der Seite "Server" (Feld "Gemeinsame Adresse der
      ASDU (CA)")
    entnommen.
    """

    rows = _load_signalliste_rows(config_path)
    sequences = {"client": send_sequence_start, "server": send_sequence_start}
    recv_sequence = recv_sequence_start

    for row in rows:
        type_id = _safe_int(row.get("IEC104- Typ"))
        if type_id <= 0:
            continue

        direction = _direction_from_row(row)
        common_address = _build_common_address(direction)
        cause = _safe_int(row.get("Übertragungsursache"), default=20)
        originator = _build_originator(direction, row)
        ioa = _build_ioa(row)
        information = _build_information_bytes(type_id, str(row.get("Wert", "")))
        frame = build_i_frame(
            send_sequence=sequences[direction],
            recv_sequence=recv_sequence,
            type_id=type_id,
            cause=cause,
            originator=originator,
            common_address=common_address,
            ioa=ioa,
            information=information,
            vsq=0,
        )
        sequences[direction] += 1
        label = _build_label(row, cause, type_id)
        yield BuiltTelegram(
            frame=frame,
            direction=direction,
            label=label,
            type_id=type_id,
            cause=cause,
            originator=originator,
            common_address=common_address,
            ioa=ioa,
            value=str(row.get("Wert", "")),
        )


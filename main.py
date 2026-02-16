#   Flask-Einstiegspunkt für das WNGW-Test-Tool
#
#   Aufgaben des Skripts:
#       1. Startet das WNGW-Test-Tool
#       2. Intitialisiert die Flask-Routen und stellt sämtliche API-Endpunkte bereit
#       3. Übernimmt Speichern von Eingaben, Verwalten von Prüfkonfigurationen, Excel-Import, Steuerung der Statusabfrage
#
#   Flask-Routen
#       1. app.route    HTML-Seite anzeigen
#       2. app.get      Daten abrufen
#       3. app.post     Informationen hochladen (posten)
#       4. app.delete   Daten löschen 


#-----------------------------------------------------------
# Import von Modulen
#-----------------------------------------------------------
from __future__ import annotations

import io
import json
import queue
import threading
import time
import uuid
import zipfile
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from jinja2 import ChoiceLoader, FileSystemLoader

from backend import backend_controller
from backend import prüfprotokoll as pruefprotokoll


#-----------------------------------------------------------
# Dateiverzeichnisse festlegen
#-----------------------------------------------------------

# 
DATA_DIR = Path("data")

#
CONFIG_DIR = DATA_DIR / "pruefungskonfigurationen"

#
COMMUNICATION_LOG_DIR = DATA_DIR / "pruefungskommunikation"

#
EXAM_SETTINGS_DIR = DATA_DIR / "einstellungen_pruefungseinstellungen"

#
LEGACY_COMMUNICATION_DIR = DATA_DIR / "einstellungen_kommunikation"

#
PROTOKOLL_DIR = DATA_DIR / "pruefprotokolle"

#
EXCEL_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


#-----------------------------------------------------------
# Import von Modulen
#-----------------------------------------------------------

# 
REQUIRED_SIGNAL_HEADERS = (
    "Datenpunkt / Meldetext",
    "IEC104- Typ",
    "IOA 3",
    "IOA 2",
    "IOA 1",
    "Übertragungsursache",
    "Herkunftsadresse",
    "Wert",
    "Qualifier",
    "Quelle/Senke von der FWK betrachtet",
    "Quelle/Senke von der NLS betrachtet",
    "GA- Generalabfrage (keine Wischer)",
)

#
FRAME_LABELS = {
    "I": "I-Format",
    "U": "U-Format",
    "S": "S-Format",
    "TCP": "TCP",
}

# 
DIRECTION_ARROWS = {
    "incoming": "←",
    "outgoing": "→",
}

# 
DEFAULT_PAUSE_BETWEEN_TESTS = 35.0
DEFAULT_INCOMING_TELEGRAM_TIMEOUT_MS = 5000.0

# 
CAUSE_MEANINGS = {
    1: "Zyklisch",
    2: "Hintergrundabfrage",
    3: "Spontan",
    4: "Initialisiert",
    6: "Aktivierung",
    7: "Bestätigung der Aktivierung",
    8: "Abbruch der Aktivierung",
    9: "Bestätigung des Abbruchs der Aktivierung",
    10: "Beendigung der Aktivierung",
    11: "Rückmeldung verursacht durch Fernbefehl",
    12: "Rückmeldung verursacht durch örtlichen Befehl",
    20: "Generalabfrage",
}

# 
ORIGINATOR_MEANINGS = {
    0: "Herkunftsadresse nicht vorhanden",
    10: "Fernsteuerung von Verteilnetz-Anlagen",
    11: "Steuerung von Kundenanlagen",
    12: "Fernsteuerung von Verteilnetz-Anlagen",
    13: "Fernsteuerung von Verteilnetz-Anlagen",
    14: "Fernsteuerung von Verteilnetz-Anlagen",
    15: "Niederspannungsmessung",
    16: "Fernsteuerung von Verteilnetz-Anlagen",
    17: "Fernsteuerung von Verteilnetz-Anlagen",
    18: "Fernsteuerung von Verteilnetz-Anlagen",
    19: "Fernsteuerung von Verteilnetz-Anlagen",
}


#-----------------------------------------------------------
# Aufzeichnung (der Kommunikation) von Teilprüfungen einrichten
#-----------------------------------------------------------

# Klasse für der Recorder der Teilprüfungen
class TeilpruefungRecorder:
    
    # Initialisiert den Recoder und legt das Zielverzeichnis an
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._active = False
        self._config_id: str = ""
        self._run_id: str = ""
        self._teil_index: int = 0
        self._entries: List[Dict[str, Any]] = []
        self._started_at: Optional[float] = None
        self._last_signal_at: Optional[float] = None
        self._recording_started = False
        self._ioa_labels: Dict[int, str] = {}

    # Parst einen IOA-Teilwert und validiert den Bereich
    @staticmethod
    def _parse_ioa_part(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if parsed < 0 or parsed > 255:
            return None
        return parsed

    # Berechnet den vollständigen IOA-Wert aus 3 Spalten
    @classmethod
    def _extract_ioa(cls, row: Dict[str, Any]) -> Optional[int]:
        parts = [
            cls._parse_ioa_part(row.get("IOA 1")),
            cls._parse_ioa_part(row.get("IOA 2")),
            cls._parse_ioa_part(row.get("IOA 3")),
        ]
        if any(part is None for part in parts):
            return None
        return parts[0] + (parts[1] << 8) + (parts[2] << 16)

    # Lädt die Meldetexte aus der gespeicherten Signalliste
    def _load_meldetexte(self) -> None:
        self._ioa_labels = {}
        file_path = _exam_signalliste_file_path()
        if not file_path.exists():
            return
        try:
            stored = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        rows = stored.get("rows")
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = row.get("Datenpunkt / Meldetext")
            if not isinstance(label, str):
                continue
            label = label.strip()
            if not label:
                continue
            ioa = self._extract_ioa(row)
            if ioa is None:
                continue
            self._ioa_labels[ioa] = label

    # Leitet den angezeigten Meldetext aus Payload und Mapping ab
    def _resolve_meldetext(self, payload: Dict[str, Any]) -> Optional[str]:
        if payload.get("frame_family") != "I":
            return None
        ioa = payload.get("ioa")
        if not isinstance(ioa, int):
            return None
        if ioa == 0:
            label = payload.get("label")
            return label if isinstance(label, str) and label else None
        mapped = self._ioa_labels.get(ioa)
        if mapped:
            return mapped
        label = payload.get("label")
        return label if isinstance(label, str) and label else None

    # Startet eine neue Aufzeichnung mit Basisdaten
    def begin(self, config_id: str, run_id: str, teil_index: int) -> None:
        self._active = True
        self._config_id = config_id or ""
        self._run_id = run_id or ""
        self._teil_index = teil_index
        self._entries = []
        self._started_at = None
        self._last_signal_at = None
        self._recording_started = False
        self._load_meldetexte()

    # Markiert den Zeitpunkt des ersten ausgesendeten Signals 
    def mark_signal_sent(self) -> None:
        if not self._active:
            return
        timestamp = time.time()
        self._last_signal_at = timestamp
        if not self._recording_started:
            self._recording_started = True
            self._started_at = timestamp

    # Beobachtet ein Telegramm-Event und protokolliert es
    def observe(self, event: Dict[str, Any]) -> None:
        if not self._active or not self._recording_started:
            return
        if not isinstance(event, dict) or event.get("type") != "telegram":
            return
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        ts = payload.get("timestamp")
        if self._started_at is not None and isinstance(ts, (int, float)):
            if ts < self._started_at:
                return
        side = payload.get("side")
        if side not in ("client", "server"):
            return
        meldetext = self._resolve_meldetext(payload)
        if meldetext:
            payload["meldetext"] = meldetext
        self._entries.append(payload)

    # Schließt die Aufzeichnung ab und speichert das Protokoll
    def finish(self, aborted: bool = False) -> None:
        if not self._active:
            return
        finished_at = time.time()
        if self._last_signal_at and not aborted:
            remaining = 5.0 - (finished_at - self._last_signal_at)
            if remaining > 0:
                time.sleep(remaining)
                finished_at = time.time()

        file_name = (
            f"{self._config_id}_teil{self._teil_index + 1}_"
            f"{self._run_id}_kommunikationsverlauf.json"
        )
        file_path = self.base_dir / file_name
        content = {
            "configurationId": self._config_id,
            "runId": self._run_id,
            "teilpruefungIndex": self._teil_index + 1,
            "aborted": bool(aborted),
            "startedAt": self._started_at,
            "finishedAt": finished_at,
            "entries": self._entries,
        }
        file_path.write_text(
            json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._active = False

    # Gibt den Zeitpunkt des letzten Signals zurück
    @property
    def last_signal_at(self) -> Optional[float]:
        return self._last_signal_at


#-----------------------------------------------------------
# Verzeichnisse anlegen und Informationen aus UI auslesen
#-----------------------------------------------------------

# Ablageordner für Prüfkonfigurationen bereitstellen
def _configurations_directory() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR

# Liefert das Verzeichnis für aktive Prüfungs-Einstellungen
def _exam_settings_directory() -> Path:
    EXAM_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return EXAM_SETTINGS_DIR

# Liefert das Verzeichnis für ältere Kommunikations-Einstellungen
def _legacy_exam_settings_directory() -> Path:
    return LEGACY_COMMUNICATION_DIR

# Liefert das Verzeichnis für die abgelegten Prüfprotokolle
def _protokoll_directory() -> Path:
    PROTOKOLL_DIR.mkdir(parents=True, exist_ok=True)
    return PROTOKOLL_DIR

# Berechnet Dateipfad zu einem gespeicherten Protokoll
def _protokoll_file_path(protocol_id: str) -> Path:
    directory = _protokoll_directory().resolve()
    file_path = (directory / f"{protocol_id}.json").resolve()
    if not str(file_path).startswith(str(directory)):
        raise ValueError("Ungültiger Speicherpfad")
    return file_path

# Baut den Pfad zu einer Kommunikations-Logdatei
def _communication_log_file_path(filename: str) -> Path:
    directory = COMMUNICATION_LOG_DIR.resolve()
    file_path = (directory / filename).resolve()
    if not str(file_path).startswith(str(directory)):
        raise ValueError("Ungültiger Speicherpfad")
    return file_path

# Ermittelt den Pfad zu einer Prüfungs-Einstellungsdatei
def _exam_settings_file_path(filename: str) -> Path:
    directory = _exam_settings_directory().resolve()
    file_path = (directory / filename).resolve()
    if not str(file_path).startswith(str(directory)):
        raise ValueError("Ungültiger Speicherpfad")
    return file_path

# Bestimmt den Pfad zu einer Alt-Einstellungsdatei
def _legacy_exam_settings_file_path(filename: str) -> Optional[Path]:
    directory = _legacy_exam_settings_directory().resolve()
    file_path = (directory / filename).resolve()
    if not str(file_path).startswith(str(directory)):
        raise ValueError("Ungültiger Speicherpfad")
    return file_path if file_path.exists() else None

# Gibt den Speicherort der importierten Signalliste zurück
def _exam_signalliste_file_path() -> Path:
    target_path = _exam_settings_file_path("signalliste.json")
    try:
        legacy_path = _legacy_exam_settings_file_path("signalliste.json")
    except ValueError:
        legacy_path = None
    if not target_path.exists() and legacy_path is not None:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            return legacy_path
    return target_path

# Liefert den Pfad zur Auswertungsvorlage
def _exam_evaluation_template_file_path() -> Path:
    return _exam_settings_file_path("auswertungsvorlage.xlsx")

# Bestimmt den Pfad zur Metadatei der Auswertungsvorlage
def _exam_evaluation_template_meta_path() -> Path:
    return _exam_settings_file_path("auswertungsvorlage.json")

# Lädt die gespeicherte Signalliste für die Prüfprotokolle
def _load_exam_signalliste_rows() -> List[Dict[str, Any]]:
    try:
        file_path = _exam_signalliste_file_path()
    except ValueError:
        return []
    if not file_path.exists():
        return []
    try:
        stored = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows = stored.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]

# Lädt die gespeicherten Einstellungen der Prüfungssteuerung
def _load_pruefungssteuerung_settings() -> Dict[str, Any]:
    try:
        file_path = _exam_settings_file_path("pruefungssteuerung.json")
    except ValueError:
        return {}
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

# Validiert eine positive Float-Eingabe und nutzt einen Defaultwert
def _parse_positive_float(raw_value: Any, default: float) -> float:
    try:
        parsed = float(str(raw_value).replace(",", "."))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default

# Liest die eingestellte Pause zwischen Tests aus
def _load_pause_between_tests(default: float = DEFAULT_PAUSE_BETWEEN_TESTS) -> float:
    stored = _load_pruefungssteuerung_settings()
    raw_value = stored.get("zeit_zwischen_pruefungen", {}).get("value")
    return _parse_positive_float(raw_value, default)

# Liest das Timeout für eingehende Telegramme aus der Konfiguration
def _load_incoming_telegram_timeout(
    default_ms: float = DEFAULT_INCOMING_TELEGRAM_TIMEOUT_MS,
) -> float:
    stored = _load_pruefungssteuerung_settings()
    raw_value = stored.get("wartezeit_telegramme_ms", {}).get("value")
    timeout_ms = _parse_positive_float(raw_value, default_ms)
    return timeout_ms / 1000.0

# Erzeugt einen Dateinamen für Protokoll- und Logdateien
def _build_log_filename(config_id: str, run_id: str, teil_index: int) -> str:
    return f"{config_id}_teil{teil_index}_{run_id}_kommunikationsverlauf.json"


def _load_telegram_entries(log_filename: Optional[str]) -> List[Dict[str, Any]]:
    if not log_filename:
        return []
    try:
        log_path = _communication_log_file_path(log_filename)
    except ValueError:
        return []
    if not log_path.exists():
        return []
    try:
        content = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = content.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


#-----------------------------------------------------------
# Darstellung der Telegramme im UI 
#-----------------------------------------------------------

# Stellt eine Zeitdifferenz in Sekunden als Text dar
def _format_delta_text(delta: Any) -> str:
    try:
        value = float(delta)
    except (TypeError, ValueError):
        return "0,000"
    return f"{max(value, 0.0):.3f}".replace(".", ",")

# Formatiert die Frame-Typ-Beschreibung für ein Telegramm
def _format_type_text(frame_family: Optional[str], type_id: Optional[int]) -> str:
    frame_label = FRAME_LABELS.get(frame_family or "", frame_family or "")
    if frame_family == "I":
        type_part = str(type_id) if type_id is not None else ""
        return f"{type_part} ({frame_label})".strip()
    if frame_label:
        return f"({frame_label})"
    return ""

# Teilt einen IOA-Wert in 3 oktettbasierte Bestandteile
def _split_ioa(ioa_value: Any) -> Optional[str]:
    if not isinstance(ioa_value, int):
        return None
    segments = [ioa_value & 0xFF, (ioa_value >> 8) & 0xFF, (ioa_value >> 16) & 0xFF]
    return " - ".join(f"{segment:03d}" for segment in segments)

# Setzt den Qualifier-Wert passend zum Label zusammen
def _format_qualifier_value(label: Optional[str], value: Any) -> str:
    if isinstance(value, (int, float)):
        value_text = format(int(value) & 0xFF, "08b")
    else:
        value_text = str(value)
    return f"{label} = {value_text}" if label else value_text

# Kombiniert Wert und Qualifier zu einem Anzeigeeintrag
def _format_value_with_qualifier(value: Any, qualifier: Any) -> Optional[str]:
    has_value = value not in (None, "")
    qualifier_label = qualifier.get("label") if isinstance(qualifier, dict) else None
    qualifier_value = qualifier.get("value") if isinstance(qualifier, dict) else None
    has_qualifier = qualifier_value is not None
    qualifier_text = _format_qualifier_value(qualifier_label, qualifier_value) if has_qualifier else ""

    if has_value and qualifier_text:
        return f"{value} ({qualifier_text})"
    if has_value:
        return str(value)
    if qualifier_text:
        return qualifier_text
    return None

# Gibt die aktuelle Bedeutung der Übertragungsursache zurück
def _format_cause_text(cause: Any) -> Optional[str]:
    if not isinstance(cause, (int, float)):
        return None
    meaning = CAUSE_MEANINGS.get(int(cause))
    return f"{int(cause)} ({meaning})" if meaning else str(int(cause))

# Liefert die textuelle Bedeutung der Herkunftsadresse
def _format_originator_text(originator: Any) -> Optional[str]:
    if not isinstance(originator, (int, float)):
        return None
    meaning = ORIGINATOR_MEANINGS.get(int(originator))
    return f"{int(originator)} ({meaning})" if meaning else str(int(originator))

# Baut den Protokolleintrag als formatierten Text zusammen
def _format_protocol_entry(entry: Dict[str, Any]) -> str:
    indent = "\t" * 6 if entry.get("side") == "server" else ""
    sequence = entry.get("sequence")
    label = entry.get("meldetext") or entry.get("label") or "Telegramm"
    header_parts = [str(sequence)] if sequence is not None else []
    if label:
        header_parts.append(str(label))
    lines = [f"{indent}{' '.join(header_parts) if header_parts else 'Telegramm'}"]

    timestamp_text = pruefprotokoll.format_timestamp_text(entry.get("timestamp"))
    delta_text = _format_delta_text(entry.get("delta"))
    lines.append(f"{indent}Time: {timestamp_text} (d = {delta_text} s)")

    arrow = DIRECTION_ARROWS.get(entry.get("direction"), "→")
    local_endpoint = entry.get("local_endpoint") or "-"
    remote_endpoint = entry.get("remote_endpoint") or "-"
    lines.append(f"{indent}IP:Port: {local_endpoint} {arrow} {remote_endpoint}")

    type_text = _format_type_text(entry.get("frame_family"), entry.get("type_id"))
    if type_text:
        lines.append(f"{indent}Typ: {type_text}")

    if entry.get("frame_family") == "I":
        cause_text = _format_cause_text(entry.get("cause"))
        if cause_text:
            lines.append(f"{indent}Ursache: {cause_text}")

        originator_text = _format_originator_text(entry.get("originator"))
        if originator_text:
            lines.append(f"{indent}Herkunft: {originator_text}")

        station = entry.get("station")
        if station is not None:
            lines.append(f"{indent}Station: {station}")

        ioa_text = _split_ioa(entry.get("ioa"))
        if ioa_text:
            lines.append(f"{indent}IOA: {ioa_text}")

        value_text = _format_value_with_qualifier(entry.get("value"), entry.get("qualifier"))
        if value_text:
            lines.append(f"{indent}Wert (Qualifier): {value_text}")

    return "\n".join(lines)

# Formatiert den Anzeigenamen eines gespeicherten Protokolls
def _format_protocol_display_name(finished_at: float, run_name: str) -> str:
    timestamp = time.localtime(finished_at)
    prefix = time.strftime("%Y.%m.%d - %H:%M Uhr", timestamp)
    name_part = run_name.strip() if isinstance(run_name, str) else ""
    return f"{prefix} - {name_part}" if name_part else prefix

# Entfernt nicht benötigte Felder aus dem gespeicherten Protokoll
def _sanitize_protocol_data(run_state: Dict[str, Any]) -> Dict[str, Any]:
    finished_at = run_state.get("finishedAt") or time.time()
    config_id = run_state.get("configurationId", "")
    run_id = run_state.get("id", "")
    teilpruefungen: List[Dict[str, Any]] = []
    for index, teil in enumerate(run_state.get("teilpruefungen", [])):
        teil_index = teil.get("index") or index + 1
        teilpruefungen.append(
            {
                "index": teil_index,
                "pruefungsart": teil.get("pruefungsart", ""),
                "status": teil.get("status", ""),
                "logFile": _build_log_filename(config_id, run_id, teil_index),
            }
        )

    sanitized = {
        "id": run_state.get("id", ""),
        "configurationId": config_id,
        "name": run_state.get("name", ""),
        "finishedAt": finished_at,
        "startedAt": run_state.get("startedAt"),
        "aborted": bool(run_state.get("aborted", False)),
        "teilpruefungen": teilpruefungen,
    }
    sanitized["displayName"] = _format_protocol_display_name(
        finished_at, sanitized.get("name", "")
    )
    return sanitized


def _sanitize_filename_component(value: Any, fallback: str = "Unbenannt") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return re.sub(r"[^\w\-\. ]+", "_", text)


#-----------------------------------------------------------
# Prüfprotokolle anlegen, speichern und entfernen
#-----------------------------------------------------------

# Persistiert ein Prüfprotokoll auf dem Datenträger
def _store_pruefprotokoll(run_state: Dict[str, Any]) -> None:
    protocol = _sanitize_protocol_data(run_state)
    try:
        file_path = _protokoll_file_path(protocol.get("id", uuid.uuid4().hex))
    except ValueError:
        return
    file_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")

# Listet alle vorhandenen Prüfprotokolle auf
def _list_protocols() -> List[Dict[str, Any]]:
    directory = _protokoll_directory()
    protocols: List[Dict[str, Any]] = []
    for file in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            protocols.append(data)
        except json.JSONDecodeError:
            continue
    return sorted(protocols, key=lambda item: item.get("finishedAt", 0), reverse=True)

# Lädt ein bestimmtes Prüfprotokoll anhand der ID
def _load_protocol(protocol_id: str) -> Dict[str, Any]:
    file_path = _protokoll_file_path(protocol_id)
    if not file_path.exists():
        raise FileNotFoundError
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ValueError("Gespeichertes Prüfprotokoll ist beschädigt.")
    return data

# Entfernt ein Prüfprotokoll aus dem Dateisystem
def _delete_protocol(protocol_id: str, protocol: Optional[Dict[str, Any]] = None) -> None:
    data = protocol or _load_protocol(protocol_id)
    teilpruefungen = data.get("teilpruefungen") if isinstance(data, dict) else []
    for teil in teilpruefungen or []:
        if not isinstance(teil, dict):
            continue
        log_file = teil.get("logFile")
        if not isinstance(log_file, str) or not log_file:
            continue
        try:
            log_path = _communication_log_file_path(log_file)
        except ValueError:
            continue
        if log_path.exists():
            log_path.unlink()
    file_path = _protokoll_file_path(protocol_id)
    if file_path.exists():
        file_path.unlink()


# Excel-Spaltenreferenz (z.B. AB12) in numerischen Index umwandeln
def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    result = 0
    for char in letters:
        result = result * 26 + (ord(char.upper()) - 64)
    return result


# Gemeinsame Zeichenketten aus einer XLSX-Datei extrahieren
def _load_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    with zf.open("xl/sharedStrings.xml") as shared_file:
        root = ET.parse(shared_file).getroot()
    strings: List[str] = []
    for si in root.findall(f"{EXCEL_NAMESPACE}si"):
        parts = [t.text or "" for t in si.findall(f".//{EXCEL_NAMESPACE}t")]
        strings.append("".join(parts))
    return strings


# Zeileninhalt eines Tabellenblatts als Mapping auslesen
def _read_sheet_rows(
    zf: zipfile.ZipFile, sheet_name: str, shared_strings: List[str]
) -> List[Dict[int, str]]:
    with zf.open(sheet_name) as sheet_file:
        root = ET.parse(sheet_file).getroot()
    sheet_data = root.find(f"{EXCEL_NAMESPACE}sheetData")
    rows: List[Dict[int, str]] = []
    if sheet_data is None:
        return rows
    for row in sheet_data.findall(f"{EXCEL_NAMESPACE}row"):
        row_values: Dict[int, str] = {}
        for cell in row.findall(f"{EXCEL_NAMESPACE}c"):
            ref = cell.attrib.get("r")
            if not ref:
                continue
            col_index = _column_index(ref)
            cell_type = cell.attrib.get("t")
            value = ""
            if cell_type == "s":
                value_node = cell.find(f"{EXCEL_NAMESPACE}v")
                if value_node is not None and value_node.text is not None:
                    shared_index = int(value_node.text)
                    if 0 <= shared_index < len(shared_strings):
                        value = shared_strings[shared_index]
            elif cell_type == "inlineStr":
                text_parts = [t.text or "" for t in cell.findall(f".//{EXCEL_NAMESPACE}t")]
                value = "".join(text_parts)
            else:
                value_node = cell.find(f"{EXCEL_NAMESPACE}v")
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
            row_values[col_index] = value
        rows.append(row_values)
    return rows


# Erste Tabelle einer Excel-Datei auslesen und in Header/Row-Struktur umwandeln
def _parse_excel_table(file_bytes: bytes) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            sheet_names = sorted(
                name
                for name in zf.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            if not sheet_names:
                raise ValueError("Keine Tabellenblätter gefunden.")
            shared_strings = _load_shared_strings(zf)
            rows = _read_sheet_rows(zf, sheet_names[0], shared_strings)
    except zipfile.BadZipFile as exc:
        raise ValueError("Die Datei ist keine gültige Excel-Datei.") from exc
    headers: List[str] = []
    parsed_rows: List[Dict[str, str]] = []
    for row_index, row_values in enumerate(rows, start=1):
        if row_index == 1:
            max_col = max(row_values.keys(), default=0)
            headers = [str(row_values.get(col, "")).strip() for col in range(1, max_col + 1)]
        else:
            if not headers:
                break
            entry: Dict[str, str] = {}
            non_empty = False
            for col_offset, header in enumerate(headers, start=1):
                value = row_values.get(col_offset, "")
                text_value = "" if value is None else str(value)
                if text_value:
                    non_empty = True
                entry[header] = text_value
            if non_empty:
                parsed_rows.append(entry)
    return {"headers": headers, "rows": parsed_rows}


# Pflichtspalten der Signalliste prüfen und fehlende Felder melden
def _validate_signal_headers(headers: List[str]) -> List[str]:
    available = set(headers)
    return [header for header in REQUIRED_SIGNAL_HEADERS if header not in available]


_QUALIFIER_PATTERN = re.compile(r"^[01]{8}$")

# Validiert, dass die Qualifier-Bits korrekt gesetzt sind
def _validate_qualifier_bits(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(_QUALIFIER_PATTERN.fullmatch(text))

# Überprüft die Qualifier-Spalte und ermittelt die Position fehlerhafter Werte
def _validate_qualifier_column(rows: List[Dict[str, Any]]) -> Optional[int]:
    for index, row in enumerate(rows, start=1):
        type_text = str(row.get("IEC104- Typ", "")).strip()
        if not type_text:
            continue
        if not _validate_qualifier_bits(row.get("Qualifier")):
            return index
    return None


# Dateipfad für eine konkrete Prüfkonfiguration ermitteln
def _configuration_file_path(config_id: str) -> Path:
    directory = _configurations_directory()
    safe_id = Path(config_id).name
    file_path = (directory / f"{safe_id}.json").resolve()
    if not str(file_path).startswith(str(directory.resolve())):
        raise ValueError("Ungültiger Konfigurationspfad")
    return file_path


# Alle vorhandenen Prüfkonfigurationen einsammeln
def _list_configurations() -> List[Dict[str, str]]:
    configurations: List[Dict[str, str]] = []
    directory = _configurations_directory()
    for file in directory.glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        config_id = data.get("id") or file.stem
        configurations.append({
            "id": config_id,
            "name": data.get("name", "Unbenannte Prüfung"),
        })
    return configurations


# Einzelne Prüfkonfiguration auslesen und anreichern
def _load_configuration(config_id: str) -> Dict[str, Any]:
    file_path = _configuration_file_path(config_id)
    if not file_path.exists():
        raise FileNotFoundError
    data = json.loads(file_path.read_text(encoding="utf-8"))
    data["id"] = data.get("id") or config_id
    teilpruefungen = data.get("teilpruefungen")
    if isinstance(teilpruefungen, list):
        for index, teil in enumerate(teilpruefungen, start=1):
            teil["index"] = index
    else:
        data["teilpruefungen"] = []
    return data


# Eingehende Prüfkonfiguration validieren und dauerhaft speichern
def _store_configuration(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Ein Name für die Prüfung ist erforderlich.")
    teilpruefungen = payload.get("teilpruefungen")
    if not isinstance(teilpruefungen, list):
        teilpruefungen = []
    normalized: List[Dict[str, Any]] = []
    for index, teil in enumerate(teilpruefungen, start=1):
        pruefungsart = teil.get("pruefungsart")
        signalliste = teil.get("signalliste")
        if not pruefungsart or not isinstance(signalliste, dict):
            continue
        headers = signalliste.get("headers") or []
        missing = _validate_signal_headers(headers)
        if missing:
            raise ValueError(
                f"Signalliste '{signalliste.get('filename', 'Unbenannt')}' fehlt: {', '.join(missing)}"
            )
        rows_data = signalliste.get("rows")
        if not isinstance(rows_data, list):
            rows_data = []
        invalid_row = _validate_qualifier_column(rows_data)
        if invalid_row is not None:
            raise ValueError(
                f"Signalliste '{signalliste.get('filename', 'Unbenannt')}' enthält einen ungültigen Qualifier in Zeile {invalid_row}."
            )
        normalized.append(
            {
                "index": index,
                "pruefungsart": pruefungsart,
                "signalliste": {
                    "filename": signalliste.get("filename", ""),
                    "headers": headers,
                    "rows": rows_data,
                },
            }
        )
    config_id = payload.get("id") or uuid.uuid4().hex
    file_path = _configuration_file_path(config_id)
    data = {
        "id": config_id,
        "name": name,
        "teilpruefungen": normalized,
    }
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


#-----------------------------------------------------------
# Prüfungen über PruefungRunner einrichten
#-----------------------------------------------------------

# Klasse für Prüfungen
class PruefungRunner:
    
    # Initialisiert den Ausführungs-Controller für Prüfungen
    def __init__(self, backend) -> None:
        self.backend = backend
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_run: Optional[Dict[str, Any]] = None
        self._events = backend.event_bus.subscribe()
        self._last_incoming: Dict[str, float] = {"client": 0.0, "server": 0.0}
        self._incoming_counts: Dict[str, int] = {"client": 0, "server": 0}
        self._recorder = TeilpruefungRecorder(COMMUNICATION_LOG_DIR)
        self._incoming_timeout_seconds = DEFAULT_INCOMING_TELEGRAM_TIMEOUT_MS / 1000.0

    # Prüft anhand des Zellinhalts, ob die Quelle senden soll
    @staticmethod
    def _should_send_from(value: object) -> bool:
        text = str(value or "").upper()
        return "Q" in text

    # Markiert alle Teilprüfungen als abgebrochen
    def _mark_all_aborted_locked(self) -> None:
        teilpruefungen = self._current_run.get("teilpruefungen", []) if self._current_run else []
        for teil in teilpruefungen:
            if teil.get("status") != "Abgeschlossen":
                teil["status"] = "Abgebrochen"

    # Markiert laufende Teilprüfungen als abgebrochen
    def _mark_all_aborted(self) -> None:
        with self._lock:
            if not self._current_run:
                return
            self._mark_all_aborted_locked()

    # Setzt den Status einer Teilprüfung im aktuellen Lauf
    def _set_status(self, index: int, status: str) -> None:
        with self._lock:
            if not self._current_run:
                return
            teilpruefungen = self._current_run.get("teilpruefungen", [])
            if 0 <= index < len(teilpruefungen):
                teilpruefungen[index]["status"] = status

    # Wartet bis zum Ablauf oder bricht bei Stop-Signal ab
    def _wait_or_abort(self, seconds: float, current_index: Optional[int] = None) -> bool:
        deadline = time.time() + max(0.0, seconds)
        while time.time() < deadline:
            if self._stop_event.wait(timeout=0.1):
                if current_index is not None:
                    self._set_status(current_index, "Abgebrochen")
                self._mark_all_aborted()
                return True
        return False

    # Liest die erwartete Telegramm-Signatur aus einer Tabellenzeile ab
    def _expected_signature(self, row: Dict[str, Any]) -> Optional[tuple]:
        type_id = int(row.get("IEC104- Typ", 0) or 0)
        if type_id <= 0:
            return None
        cause = int(row.get("Übertragungsursache", 20) or 20)
        ioa1 = int(row.get("IOA 1", 0) or 0) & 0xFF
        ioa2 = int(row.get("IOA 2", 0) or 0) & 0xFF
        ioa3 = int(row.get("IOA 3", 0) or 0) & 0xFF
        ioa = ioa1 | (ioa2 << 8) | (ioa3 << 16)
        return (type_id, cause, ioa)

    # Holt neue Ereignisse aus der Backend-Queue und aktualisiert Zähler
    def _pull_events(
        self,
        pending: Optional[Dict[str, List[tuple]]] = None,
        consider_from: Optional[float] = None,
    ) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if not isinstance(event, dict):
                continue
            self._recorder.observe(event)
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            if (
                event.get("type") == "telegram"
                and payload.get("frame_family") == "I"
                and payload.get("direction") == "incoming"
            ):
                ts = payload.get("timestamp")
                if (
                    consider_from is not None
                    and isinstance(ts, (int, float))
                    and ts < consider_from
                ):
                    continue
                side = payload.get("side")
                if side in self._last_incoming:
                    self._last_incoming[side] = time.time()
                    self._incoming_counts[side] = self._incoming_counts.get(side, 0) + 1
                if pending is not None and isinstance(pending, dict):
                    signature = (
                        payload.get("type_id"),
                        payload.get("cause"),
                        payload.get("ioa"),
                    )
                    pending_list = pending.get(side)
                    if pending_list is not None and signature[0] is not None:
                        for index, expected in enumerate(list(pending_list)):
                            if expected == signature:
                                pending_list.pop(index)
                                break

    # Warten auf eingehende Antworten der Gegenseite 
    def _wait_for_turn(
        self,
        side: str,
        pending: Dict[str, List[tuple]],
        expected_counts: Dict[str, Optional[int]],
        consider_from: Optional[float],
    ) -> None:
        start = time.time()
        deadline = start + self._incoming_timeout_seconds
        while not self._stop_event.is_set():
            self._pull_events(pending, consider_from)
            expected_target = expected_counts.get(side)
            if expected_target is not None and self._incoming_counts.get(side, 0) >= expected_target:
                expected_counts[side] = None
            if not pending.get(side) and expected_counts.get(side) is None:
                return
            if time.time() >= deadline:
                pending[side] = []
                expected_counts[side] = None
                return
            time.sleep(0.05)

    # Gruppiert Signale nach Absenderseite 
    def _build_signal_segments(self, rows: List[Dict[str, Any]]):
        sequence: List[Dict[str, Any]] = []
        for row in rows:
            sides: List[str] = []
            if self._should_send_from(row.get("Quelle/Senke von der NLS betrachtet")):
                sides.append("client")
            if self._should_send_from(row.get("Quelle/Senke von der FWK betrachtet")):
                sides.append("server")
            for side in sides:
                sequence.append({"side": side, "row": row})
        segments: List[Dict[str, Any]] = []
        for entry in sequence:
            if segments and segments[-1]["side"] == entry["side"]:
                segments[-1]["rows"].append(entry["row"])
            else:
                segments.append({"side": entry["side"], "rows": [entry["row"]]})
        return segments

    # Schließt einen Lauf ab und speichert die Ergebnisse
    def _mark_finished(self, aborted: bool = False) -> None:
        with self._lock:
            if not self._current_run:
                return
            if aborted:
                self._mark_all_aborted_locked()
                self._current_run["aborted"] = True
            else:
                self._current_run["aborted"] = False
            self._current_run["finished"] = True
            self._current_run["finishedAt"] = time.time()
            try:
                _store_pruefprotokoll(self._current_run)
            except Exception:
                pass

    # Liefert den öffentlich nutzbaren Status des aktuellen Laufs
    def _copy_public_state(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._current_run:
                return None
            clone = json.loads(json.dumps(self._current_run))
            for teil in clone.get("teilpruefungen", []):
                signalliste = teil.get("signalliste")
                if isinstance(signalliste, dict):
                    teil["signalliste"] = {"filename": signalliste.get("filename", "")}
            return clone

    # Sendet die Signalsegmente an Client oder Server
    def _dispatch_signals(self, rows: List[Dict[str, Any]]) -> None:
        segments = self._build_signal_segments(rows)
        pending: Dict[str, List[tuple]] = {"client": [], "server": []}
        expected_counts: Dict[str, Optional[int]] = {"client": None, "server": None}
        consider_from: Optional[float] = None
        self._incoming_counts = {"client": 0, "server": 0}
        self._last_incoming = {"client": 0.0, "server": 0.0}
        for index, segment in enumerate(segments):
            if self._stop_event.is_set():
                break
            other_side = "server" if segment["side"] == "client" else "client"
            if pending.get(segment["side"]) or expected_counts.get(segment["side"]) is not None:
                self._wait_for_turn(segment["side"], pending, expected_counts, consider_from)
            for row in segment["rows"]:
                if self._stop_event.is_set():
                    break
                if consider_from is None:
                    consider_from = time.time()
                self._recorder.mark_signal_sent()
                self.backend.send_signal(segment["side"], row)
                time.sleep(0.05)
            expected_counts[other_side] = self._incoming_counts.get(other_side, 0) + len(segment["rows"])
            for row in segment["rows"]:
                signature = self._expected_signature(row)
                if signature:
                    pending.setdefault(other_side, []).append(signature)
            self._pull_events(pending, consider_from)

    # Wartet nach dem letzten ausgesendeten Signal auf Antworten
    def _wait_after_last_signal(self) -> None:
        last_signal = self._recorder.last_signal_at
        if last_signal is None:
            return
        deadline = last_signal + self._incoming_timeout_seconds
        while not self._stop_event.is_set() and time.time() < deadline:
            self._pull_events()
            time.sleep(0.05)
        self._pull_events()

    # Hauptablauf zur Durchführung aller Teilprüfungen
    def _run(self, run_state: Dict[str, Any]) -> None:
        aborted = False
        self.backend.start_client()
        self.backend.start_server()
        self.backend.set_test_active(True)
        try:
            teilpruefungen = run_state.get("teilpruefungen", [])
            config_id = run_state.get("configurationId", "")
            pause_seconds = _load_pause_between_tests()
            self._incoming_timeout_seconds = _load_incoming_telegram_timeout()
            for index, teil in enumerate(teilpruefungen):
                self._recorder.begin(config_id, run_state.get("id", ""), index)
                teil_aborted = False
                if self._stop_event.is_set():
                    aborted = True
                    teil_aborted = True
                    self._recorder.finish(aborted=True)
                    break
                self._set_status(index, "Vorbereiten")
                rows = []
                signalliste = teil.get("signalliste")
                if isinstance(signalliste, dict):
                    rows = signalliste.get("rows") or []
                if self._wait_or_abort(pause_seconds, index):
                    aborted = True
                    teil_aborted = True
                    self._recorder.finish(aborted=True)
                    break
                if self._stop_event.is_set():
                    aborted = True
                    teil_aborted = True
                    self._recorder.finish(aborted=True)
                    break
                self._set_status(index, "Wird durchgeführt")
                self._dispatch_signals(rows)
                self._wait_after_last_signal()
                if self._stop_event.is_set():
                    aborted = True
                    teil_aborted = True
                    self._recorder.finish(aborted=True)
                    break
                self._set_status(index, "Abgeschlossen")
                self._recorder.finish(aborted=False)
        finally:
            self.backend.set_test_active(False)
            self._mark_finished(aborted=aborted)

    # Startet einen neuen Prüfungsdurchlauf
    def start(self, config_id: str) -> Dict[str, Any]:
        configuration = _load_configuration(config_id)
        teilpruefungen: List[Dict[str, Any]] = []
        for teil in configuration.get("teilpruefungen", []):
            teilpruefungen.append(
                {
                    "index": teil.get("index", len(teilpruefungen) + 1),
                    "pruefungsart": teil.get("pruefungsart", ""),
                    "signalliste": teil.get("signalliste", {}),
                    "status": "In Warteschlange",
                }
            )

        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Eine Prüfung läuft bereits.")
            self._stop_event = threading.Event()
            self._current_run = {
                "id": uuid.uuid4().hex,
                "configurationId": configuration.get("id", config_id),
                "name": configuration.get("name", ""),
                "teilpruefungen": teilpruefungen,
                "finished": False,
                "startedAt": time.time(),
            }
            thread = threading.Thread(
                target=self._run, args=(self._current_run,), daemon=True
            )
            self._thread = thread
            thread.start()
        return self._copy_public_state() or {}

    # Bricht den aktuellen Prüfungsdurchlauf ab und liefert Status 
    def abort(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._current_run:
                return None
            self._stop_event.set()
            self._mark_all_aborted_locked()
        return self._copy_public_state()

    # Gibt den aktuellen Status des Prüfungsdurchlaufs zurück
    def status(self) -> Optional[Dict[str, Any]]:
        return self._copy_public_state()


#-----------------------------------------------------------
# Einträge in Frontend setzen und Einträge aus Formularen abrufen
#-----------------------------------------------------------

# Beim Wechsel auf die "Beobachten"-Seite sollen 1000 Telegramme aus der JSON-Datei geladen und angezeigt werden
# Wert muss ebenfalls im Skript "beobachten.js" bearbeitet werden
DEFAULT_HISTORY_LIMIT = 1000


# Flask-App mit Frontend-Templates und statischen Dateien initialisieren
def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="frontend/templates",
        static_folder="frontend/static",
    )

    # Templates aus Seiten- und Komponentenverzeichnis laden
    app.jinja_loader = ChoiceLoader(
        [
            FileSystemLoader("frontend/templates"),
            FileSystemLoader("frontend/components"),
        ]
    )

    # Meta-Informationen für die Seiten des Frontends
    pages = {
        "startseite": {
            "heading": "Startseite",
            "description": "Überblick über das WNGW-Test-Tool und schnelle Navigation zu den wichtigsten Bereichen.",
        },
        "beobachten": {
            "heading": "Beobachten",
            "description": "Live-Monitoring laufender Tests, Statusmeldungen und relevante Kennzahlen im Blick.",
        },
        "pruefung_starten": {
            "heading": "Prüfung starten",
            "description": "Konfigurieren und starten Sie neue Testläufe mit den gewünschten Parametern.",
        },
        "pruefung_konfigurieren": {
            "heading": "Prüfung konfigurieren",
            "description": "Definieren Sie Prüfprofile, Zeitpläne und Ressourcen für wiederkehrende Abläufe.",
        },
        "pruefprotokolle": {
            "heading": "Prüfprotokolle",
            "description": "Analysieren Sie abgeschlossene Prüfungen und exportieren Sie Protokolle zur Dokumentation.",
        },
        "einstellungen_client": {
            "heading": "Client",
            "description": "Verwalten Sie clientseitige Parameter wie IP-Adressen, Zeitüberwachungen und Flusskontrollparameter. Der Client-Prozess nimmt im WNGW-Test-Tool die Rolle der Leitstelle ein.",
        },
        "einstellungen_server": {
            "heading": "Server",
            "description": "Verwalten Sie serverseitige Parameter wie IP-Adressen, Zeitüberwachungen und Flusskontrollparameter. Der Server-Prozess nimmt im WNGW-Test-Tool die Rolle der Kundenstation ein.",
        },
        "einstellungen_pruefungseinstellungen": {
            "heading": "Prüfungseinstellungen",
            "description": "Signallisten sowie Prüfungsabstände konfigurieren.",
        },
        "einstellungen_allgemein": {
            "heading": "Allgemein",
            "description": "Darstellung, Sprache und Reset-Optionen.",
        },
        "referenzen": {
            "heading": "Referenzen",
            "description": "Ansprechpartner für technische Entwicklung und Produkt-Management.",
        },
    }

    # Pfad für das Zwischenspeichern der Eingabefelder pro Seite/Komponente
    def _input_box_file_path(page_key: str, component_id: str) -> Path:
        relative = Path(page_key) / f"{component_id}.json"
        file_path = (DATA_DIR / relative).resolve()
        if not str(file_path).startswith(str(DATA_DIR.resolve())):
            raise ValueError("Ungültiger Speicherpfad")
        return file_path

    # Standardwerte für dynamische Eingabefelder erzeugen
    def _default_input_box_values(
        columns: List[Dict[str, Any]], rows: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        defaults: Dict[str, Dict[str, str]] = {}
        for row in rows:
            row_defaults: Dict[str, str] = {}
            for column in columns:
                if column.get("type") == "input":
                    row_defaults[column["key"]] = ""
            if row_defaults:
                defaults[row["id"]] = row_defaults
        return defaults

    # Gespeicherte Eingabewerte laden und mit Standardwerten mergen
    def load_input_box_values(
        page_key: str, component_id: str, columns: List[Dict[str, Any]], rows: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        defaults = _default_input_box_values(columns, rows)
        try:
            file_path = _input_box_file_path(page_key, component_id)
        except ValueError:
            return defaults
        if file_path.exists():
            try:
                stored = json.loads(file_path.read_text(encoding="utf-8"))
                for row_id, row_values in stored.items():
                    if row_id in defaults:
                        for column_key, value in row_values.items():
                            if column_key in defaults[row_id]:
                                defaults[row_id][column_key] = value
            except json.JSONDecodeError:
                pass
        return defaults

    pruefung_runner = PruefungRunner(backend_controller)

    # Hilfsfunktionen für Formulare im Template-Kontext verfügbar machen
    @app.context_processor
    def inject_input_box_helpers():
        return {
            "input_box_values": load_input_box_values,
        }

    # Gemeinsame Renderer für die statischen Seiten bereitstellen
    def render_page(page_key: str, active_page: str):
        page = pages.get(page_key, {})
        return render_template(
            "base.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page=active_page,
        )


#-----------------------------------------------------------
# Flask-Routen definieren
#-----------------------------------------------------------

    # Flask-Route: Seite "Startseite"
    @app.route("/")
    def startseite():
        return render_page("startseite", "startseite")

    # Flask-Route: Seite "Beobachten"
    @app.route("/beobachten")
    def beobachten():
        page = pages.get("beobachten", {})
        return render_template(
            "beobachten.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="beobachten",
        )

    # Flask-Route: Seite "Prüfung starten"
    @app.route("/pruefung/starten")
    def pruefung_starten():
        page = pages.get("pruefung_starten", {})
        return render_template(
            "pruefung_starten.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="pruefung_starten",
        )

    # Flask-Route: Seite "Prüfung konfigurieren"
    @app.route("/pruefung/konfigurieren")
    def pruefung_konfigurieren():
        page = pages.get("pruefung_konfigurieren", {})
        return render_template(
            "pruefung_konfigurieren.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="pruefung_konfigurieren",
        )

    # Flask-Route: Seite "Prüfprotokolle"
    @app.route("/pruefung/protokolle")
    def pruefprotokolle():
        page = pages.get("pruefprotokolle", {})
        return render_template(
            "pruefprotokolle.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="pruefung_protokolle",
        )

    # Flask-Route: Seite "Client"
    @app.route("/einstellungen/client")
    def einstellungen_client():
        page = pages.get("einstellungen_client", {})
        return render_template(
            "client.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="einstellungen_client",
        )

    # Flask-Route: Seite "Server"
    @app.route("/einstellungen/server")
    def einstellungen_server():
        page = pages.get("einstellungen_server", {})
        return render_template(
            "server.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="einstellungen_server",
        )

    # Flask-Route: Seite "Prüfungseinstellungen"
    @app.route("/einstellungen/pruefungseinstellungen")
    def einstellungen_pruefungseinstellungen():
        page = pages.get("einstellungen_pruefungseinstellungen", {})
        return render_template(
            "pruefungseinstellungen.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="einstellungen_pruefungseinstellungen",
            default_pause_between_tests=DEFAULT_PAUSE_BETWEEN_TESTS,
            default_incoming_telegram_timeout_ms=DEFAULT_INCOMING_TELEGRAM_TIMEOUT_MS,
        )

    # Flask-Route: Seite "Allgemein"
    @app.route("/einstellungen/allgemein")
    def einstellungen_allgemein():
        return render_page("einstellungen_allgemein", "einstellungen_allgemein")

    # Flask-Route: Seite "Referenzen"
    @app.route("/referenzen")
    def referenzen():
        page = pages.get("referenzen", {})
        return render_template(
            "referenzen.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="referenzen",
        )

    # Flask-Route: API-Endpunkte für UI-Interaktionen 
    # Eingaben aus dynamischen Input-Boxen abspeichern
    @app.post("/api/components/input-box/save")
    def save_input_box():
        payload = request.get_json(silent=True) or {}
        component_id = payload.get("componentId")
        page_key = payload.get("pageKey")
        values = payload.get("values")

        if not component_id or not page_key or not isinstance(values, dict):
            return jsonify({"status": "error", "message": "Ungültige Anfrage."}), 400

        try:
            file_path = _input_box_file_path(page_key, component_id)
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8")

        return jsonify({"status": "success", "message": "Eingaben gespeichert."})

    # Flask-Route: Statische Dateien für Komponenten ausliefern
    @app.route("/components/<path:filename>")
    def component_asset(filename: str):
        return send_from_directory("frontend/components", filename)

    # Flask-Route: Verfügbare Prüfkonfigurationen als Liste zurückgeben
    @app.get("/api/pruefungskonfigurationen")
    def api_list_configurations():
        configs = sorted(
            _list_configurations(), key=lambda item: item.get("name", "").lower()
        )
        return jsonify({"configurations": configs})

    # Flask-Route: Notwendige Spaltenüberschriften für Signallisten bereitstellen
    @app.get("/api/pruefungskonfigurationen/required_headers")
    def api_required_signal_headers():
        return jsonify({"headers": list(REQUIRED_SIGNAL_HEADERS)})

    # Flask-Route: Einzelne Prüfkonfiguration abrufen
    @app.get("/api/pruefungskonfigurationen/<config_id>")
    def api_get_configuration(config_id: str):
        try:
            configuration = _load_configuration(config_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Konfiguration nicht gefunden."}), 404
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültige Konfiguration."}), 400
        return jsonify({"configuration": configuration})

    # Flask-Route: Neue oder aktualisierte Prüfkonfiguration speichern
    @app.post("/api/pruefungskonfigurationen")
    def api_save_configuration():
        payload = request.get_json(silent=True) or {}
        try:
            configuration = _store_configuration(payload)
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        return jsonify({"status": "success", "configuration": configuration})

    # Flask-Route: Prüfkonfiguration löschen
    @app.delete("/api/pruefungskonfigurationen/<config_id>")
    def api_delete_configuration(config_id: str):
        try:
            file_path = _configuration_file_path(config_id)
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültige Konfiguration."}), 400
        if not file_path.exists():
            return jsonify({"status": "error", "message": "Konfiguration nicht gefunden."}), 404
        file_path.unlink()
        return jsonify({"status": "success"})

    # Flask-Route: Prüfprotokolle als Liste zurückgeben
    # Listet alle abgelegten Prüfprotokolle
    @app.get("/api/pruefprotokolle")
    def api_list_pruefprotokolle():
        protocols = []
        for item in _list_protocols():
            finished_at = item.get("finishedAt") or time.time()
            display_name = item.get("displayName") or _format_protocol_display_name(
                finished_at, item.get("name", "")
            )
            protocols.append(
                {
                    "id": item.get("id", ""),
                    "displayName": display_name,
                    "name": item.get("name", ""),
                    "finishedAt": finished_at,
                }
            )
        return jsonify({"status": "success", "protocols": protocols})

    # Flask-Route: Einzelnes Prüfprotokoll abrufen
    # Lädt ein spezifisches Prüfprotokoll
    @app.get("/api/pruefprotokolle/<protocol_id>")
    def api_get_pruefprotokoll(protocol_id: str):
        try:
            data = _load_protocol(protocol_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Protokoll nicht gefunden."}), 404
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500
        finished_at = data.get("finishedAt") or time.time()
        if "displayName" not in data:
            data["displayName"] = _format_protocol_display_name(
                finished_at, data.get("name", "")
            )
        return jsonify({"status": "success", "protocol": data})

    @app.get("/api/pruefprotokolle/<protocol_id>/teilpruefungen/<int:teil_index>/excel")
    def api_download_pruefprotokoll_excel(protocol_id: str, teil_index: int):
        try:
            protocol = _load_protocol(protocol_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Protokoll nicht gefunden."}), 404
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

        config_id = protocol.get("configurationId")
        if not config_id:
            return jsonify({"status": "error", "message": "Zuordnung zur Prüfung fehlt."}), 404

        try:
            configuration = _load_configuration(config_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Prüfung nicht gefunden."}), 404
        except ValueError:
            return jsonify({"status": "error", "message": "Prüfung beschädigt."}), 500

        teil_config = None
        for teil in configuration.get("teilpruefungen", []):
            if int(teil.get("index", -1)) == int(teil_index):
                teil_config = teil
                break

        if not teil_config:
            return jsonify({"status": "error", "message": "Teilprüfung nicht gefunden."}), 404

        teil_protocol = None
        for teil in protocol.get("teilpruefungen", []):
            if int(teil.get("index", -1)) == int(teil_index):
                teil_protocol = teil
                break

        log_file = teil_protocol.get("logFile") if isinstance(teil_protocol, dict) else None
        telegram_entries = _load_telegram_entries(log_file)
        signalliste_rows = _load_exam_signalliste_rows()

        incoming_timeout = _load_incoming_telegram_timeout()
        excel_content = pruefprotokoll.build_protocol_excel(
            telegram_entries,
            signalliste_rows,
            incoming_telegram_timeout=incoming_timeout,
        )

        run_name = protocol.get("name") or configuration.get("name") or "Pruefung"
        pruefungsart = teil_config.get("pruefungsart") or "Teilpruefung"
        filename = (
            f"Prüfprotokoll_{_sanitize_filename_component(run_name, 'Pruefung')}_"
            f"Teilprüfung {teil_index}_{_sanitize_filename_component(pruefungsart)}.xlsx"
        )

        return Response(
            excel_content,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )

    # Flask-Route: Einzelnen Teil eines Prüfprotokolls herunterladen
    # Stellt die Kommunikationslogdatei einer Teilprüfung bereit
    @app.get("/api/pruefprotokolle/<protocol_id>/teilpruefungen/<int:teil_index>/log")
    def api_download_pruefprotokoll(protocol_id: str, teil_index: int):
        try:
            data = _load_protocol(protocol_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Protokoll nicht gefunden."}), 404
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

        matching = None
        for teil in data.get("teilpruefungen", []):
            if int(teil.get("index", -1)) == int(teil_index):
                matching = teil
                break
        if not matching:
            return jsonify({"status": "error", "message": "Teilprüfung nicht gefunden."}), 404

        log_file = matching.get("logFile")
        if not isinstance(log_file, str) or not log_file:
            return jsonify({"status": "error", "message": "Kein Protokoll verfügbar."}), 404
        try:
            log_path = _communication_log_file_path(log_file)
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Dateipfad."}), 400
        if not log_path.exists():
            return jsonify({"status": "error", "message": "Protokoll nicht gefunden."}), 404
        try:
            log_content = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "Protokoll beschädigt."}), 500

        entries = [
            _format_protocol_entry(entry) for entry in log_content.get("entries", []) if isinstance(entry, dict)
        ]
        if not entries:
            entries.append("Keine Telegramme vorhanden.")

        download_name = Path(log_path.name).with_suffix(".txt").name
        return Response(
            "\n\n".join(entries),
            mimetype="text/plain",
            headers={"Content-Disposition": f"attachment; filename={download_name}"},
        )

    # Flask-Route: Prüfprotokoll löschen
    # Entfernt ein Prüfprotokoll samt Dateien
    @app.delete("/api/pruefprotokolle/<protocol_id>")
    def api_delete_pruefprotokoll(protocol_id: str):
        try:
            protocol = _load_protocol(protocol_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Protokoll nicht gefunden."}), 404
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

        try:
            _delete_protocol(protocol_id, protocol)
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Protokollpfad."}), 400
        return jsonify({"status": "success"})

    # Flask-Route: Prüfungsdurchlauf starten
    # Startet den Prüfthread mit ausgewählter Konfiguration
    @app.post("/api/pruefungslauf/start")
    def api_start_pruefungslauf():
        payload = request.get_json(silent=True) or {}
        config_id = payload.get("configId")
        if not config_id:
            return jsonify({"status": "error", "message": "Keine Prüfung ausgewählt."}), 400
        try:
            run_state = pruefung_runner.start(config_id)
        except FileNotFoundError:
            return jsonify({"status": "error", "message": "Konfiguration nicht gefunden."}), 404
        except RuntimeError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        return jsonify({"status": "success", "run": run_state})

    # Flask-Route: Status des laufenden Prüfungsdurchlaufs abfragen
    @app.get("/api/pruefungslauf/status")
    def api_status_pruefungslauf():
        return jsonify({"run": pruefung_runner.status()})

    # Flask-Route: Laufende Prüfung abbrechen
    @app.post("/api/pruefungslauf/abbrechen")
    def api_abort_pruefungslauf():
        state = pruefung_runner.abort()
        status = "aborted" if state else "idle"
        return jsonify({"status": status, "run": state})

    # Flask-Route: Signalliste im XLSX-Format entgegennehmen und prüfen
    @app.post("/api/pruefungskonfigurationen/signalliste")
    def api_upload_signalliste():
        file = request.files.get("signalliste")
        if file is None or file.filename == "":
            return jsonify({"status": "error", "message": "Keine Datei ausgewählt."}), 400
        filename = file.filename
        if not filename.lower().endswith(".xlsx"):
            return jsonify({"status": "error", "message": "Es werden nur .xlsx-Dateien unterstützt."}), 400
        file_bytes = file.read()
        try:
            parsed = _parse_excel_table(file_bytes)
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        missing = _validate_signal_headers(parsed.get("headers", []))
        if missing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Signalliste unvollständig: " + ", ".join(missing),
                    }
                ),
                400,
            )
        invalid_row = _validate_qualifier_column(parsed.get("rows", []))
        if invalid_row is not None:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Ungültiger Qualifier in Zeile {invalid_row}: Es werden genau 8 Bits (0 oder 1) erwartet.",
                    }
                ),
                400,
            )
        parsed["filename"] = filename
        return jsonify(parsed)

    # Flask-Route: Signalliste für die Prüfungseinstellungen abrufen
    @app.get("/api/einstellungen/pruefungseinstellungen/signalliste")
    def api_get_pruefungseinstellungen_signalliste():
        try:
            file_path = _exam_signalliste_file_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400
        if not file_path.exists():
            return jsonify({"status": "empty"})
        try:
            stored = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "Gespeicherte Signalliste ist beschädigt."}), 500
        return jsonify({"status": "success", "signalliste": stored})

    # Flask-Route: Signalliste für die Prüfungseinstellungen speichern
    @app.post("/api/einstellungen/pruefungseinstellungen/signalliste")
    def api_save_pruefungseinstellungen_signalliste():
        file = request.files.get("signalliste")
        if file is None or file.filename == "":
            return jsonify({"status": "error", "message": "Keine Datei ausgewählt."}), 400
        filename = file.filename
        if not filename.lower().endswith(".xlsx"):
            return jsonify({"status": "error", "message": "Es werden nur .xlsx-Dateien unterstützt."}), 400
        try:
            parsed = _parse_excel_table(file.read())
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400
        missing = _validate_signal_headers(parsed.get("headers", []))
        if missing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Signalliste unvollständig: " + ", ".join(missing),
                    }
                ),
                400,
            )
        invalid_row = _validate_qualifier_column(parsed.get("rows", []))
        if invalid_row is not None:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Ungültiger Qualifier in Zeile {invalid_row}: Es werden genau 8 Bits (0 oder 1) erwartet.",
                    }
                ),
                400,
            )
        payload = {
            "filename": filename,
            "headers": parsed.get("headers", []),
            "rows": parsed.get("rows", []),
        }
        try:
            file_path = _exam_signalliste_file_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"status": "success", "signalliste": payload})

    @app.get("/api/einstellungen/pruefungseinstellungen/auswertungsvorlage")
    def api_get_pruefungseinstellungen_auswertungsvorlage():
        try:
            file_path = _exam_evaluation_template_file_path()
            meta_path = _exam_evaluation_template_meta_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400

        if not file_path.exists() or not meta_path.exists():
            return jsonify({"status": "empty"})

        try:
            stored = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "Gespeicherte Vorlage ist beschädigt."}), 500

        return jsonify({"status": "success", "auswertungsvorlage": stored})

    # Flask-Route: Auswertungsvorlage speichern
    # Speichert die bereitgestellte Auswertungsvorlage ab
    @app.post("/api/einstellungen/pruefungseinstellungen/auswertungsvorlage")
    def api_save_pruefungseinstellungen_auswertungsvorlage():
        file = request.files.get("auswertungsvorlage")
        if file is None or file.filename == "":
            return jsonify({"status": "error", "message": "Keine Datei ausgewählt."}), 400

        filename = file.filename
        if not filename.lower().endswith(".xlsx"):
            return jsonify({"status": "error", "message": "Es werden nur .xlsx-Dateien unterstützt."}), 400

        meta = {"filename": filename}

        try:
            file_path = _exam_evaluation_template_file_path()
            meta_path = _exam_evaluation_template_meta_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file.read())
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        return jsonify({"status": "success", "auswertungsvorlage": meta})

    # Client starten
    @app.post("/api/backend/client/start")
    def api_start_client():
        started = backend_controller.start_client()
        status = "started" if started else "already_running"
        return jsonify({"status": status})

    # Server starten
    @app.post("/api/backend/server/start")
    def api_start_server():
        started = backend_controller.start_server()
        status = "started" if started else "already_running"
        return jsonify({"status": status})

    # Client stoppen
    @app.post("/api/backend/client/stop")
    def api_stop_client():
        stopped = backend_controller.stop_client()
        status = "stopped" if stopped else "not_running"
        return jsonify({"status": status})

    # Server stoppen
    @app.post("/api/backend/server/stop")
    def api_stop_server():
        stopped = backend_controller.stop_server()
        status = "stopped" if stopped else "not_running"
        return jsonify({"status": status})

    # Kommunikationsverlauf aus dem Backend abrufen
    @app.get("/api/backend/history")
    def api_history():
        raw_limit = request.args.get("limit", type=int)
        if raw_limit is None:
            limit = DEFAULT_HISTORY_LIMIT
        elif raw_limit <= 0:
            limit = None
        else:
            limit = raw_limit
        history = backend_controller.history.load_all(limit=limit)
        return jsonify(history)

    # Aktuellen Verbindungsstatus des Backends liefern
    @app.get("/api/backend/status")
    def api_backend_status():
        return jsonify(backend_controller.get_connection_status())

    # Kommunikationsverlauf löschen
    @app.post("/api/backend/history/<side>/clear")
    def api_history_clear(side: str):
        try:
            backend_controller.history.clear(side)
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültige Seite."}), 400
        return jsonify({"status": "success"})

    # Live-Events des Backends als Stream bereitstellen
    @app.route("/api/backend/stream")
    def api_backend_stream():
        subscriber = backend_controller.event_bus.subscribe()

        # Ereignisse aus dem Backend als Server-Sent-Event ausliefern
        def event_stream():
            try:
                while True:
                    event = subscriber.get()
                    if event is None:
                        break
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                backend_controller.event_bus.unsubscribe(subscriber)

        return Response(event_stream(), mimetype="text/event-stream")

    # Vollständig konfigurierte Flask-App an den Aufruf zurückgeben
    return app


#-----------------------------------------------------------
# Programm starten
#-----------------------------------------------------------

# Lokaler Einstiegspunkt zum Starten der Anwendung 
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

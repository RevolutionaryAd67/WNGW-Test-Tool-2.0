#   Flask-Einstiegspunkt für das WNGW-Test-Tool
#
#   Aufgaben des Skripts:
#       1. Startet das WNGW-Test-Tool
#       2. Intitialisiert die Flask-Routen und stellt sämtliche API-Endpunkte bereit
#       3. Übernimmt Speichern von Eingaben, Verwalten von Prüfkonfigurationen, Excel-Import, Steuerung der Statusabfrage

from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from jinja2 import ChoiceLoader, FileSystemLoader

from backend import backend_controller

DATA_DIR = Path("data")
CONFIG_DIR = DATA_DIR / "pruefungskonfigurationen"
COMMUNICATION_DIR = DATA_DIR / "einstellungen_kommunikation"
EXCEL_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REQUIRED_SIGNAL_HEADERS = {
    "Datenpunkt / Meldetext",
    "IOA 3",
    "IOA 2",
    "IOA 1",
    "IEC104- Typ",
}

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
        "einstellungen_kommunikation": {
            "heading": "Kommunikation",
            "description": "Signallisten für den Server verwalten und bereitstellen.",
        },
        "einstellungen_allgemein": {
            "heading": "Allgemein",
            "description": "Darstellung, Sprache und Reset-Optionen.",
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

    # Ablageordner für Prüfkonfigurationen bereitstellen
    def _configurations_directory() -> Path:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return CONFIG_DIR

    # Ablageordner für Kommunikationssignallisten bereitstellen
    def _communication_directory() -> Path:
        COMMUNICATION_DIR.mkdir(parents=True, exist_ok=True)
        return COMMUNICATION_DIR

    # Standard-Dateipfad für die hinterlegte Kommunikations-Signalliste ermitteln
    def _communication_file_path() -> Path:
        directory = _communication_directory()
        file_path = (directory / "signalliste.json").resolve()
        if not str(file_path).startswith(str(directory.resolve())):
            raise ValueError("Ungültiger Speicherpfad")
        return file_path

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
        return sorted(header for header in REQUIRED_SIGNAL_HEADERS if header not in available)

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
        return render_page("pruefprotokolle", "pruefung_protokolle")

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

    # Flask-Route: Seite "Kommunikation"
    @app.route("/einstellungen/server/kommunikation")
    def einstellungen_kommunikation():
        page = pages.get("einstellungen_kommunikation", {})
        return render_template(
            "kommunikation.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page="einstellungen_kommunikation",
        )

    # Flask-Route: Seite "Allgemein"
    @app.route("/einstellungen/allgemein")
    def einstellungen_allgemein():
        return render_page("einstellungen_allgemein", "einstellungen_allgemein")

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
        parsed["filename"] = filename
        return jsonify(parsed)

    # Flask-Route: Signalliste für die Kommunikationsseite abrufen
    @app.get("/api/einstellungen/kommunikation/signalliste")
    def api_get_kommunikation_signalliste():
        try:
            file_path = _communication_file_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400
        if not file_path.exists():
            return jsonify({"status": "empty"})
        try:
            stored = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "Gespeicherte Signalliste ist beschädigt."}), 500
        return jsonify({"status": "success", "signalliste": stored})

    # Flask-Route: Signalliste für die Kommunikationsseite speichern
    @app.post("/api/einstellungen/kommunikation/signalliste")
    def api_save_kommunikation_signalliste():
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
        payload = {
            "filename": filename,
            "headers": parsed.get("headers", []),
            "rows": parsed.get("rows", []),
        }
        try:
            file_path = _communication_file_path()
        except ValueError:
            return jsonify({"status": "error", "message": "Ungültiger Speicherort."}), 400
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"status": "success", "signalliste": payload})

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


# Lokaler Einstiegspunkt zum Starten der Anwendung 
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

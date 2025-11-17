from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request, send_from_directory
from jinja2 import ChoiceLoader, FileSystemLoader


DATA_DIR = Path("data")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="frontend/templates",
        static_folder="frontend/static",
    )

    app.jinja_loader = ChoiceLoader(
        [
            FileSystemLoader("frontend/templates"),
            FileSystemLoader("frontend/components"),
        ]
    )

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
            "description": "Verwalten Sie clientseitige Parameter wie Benutzerrollen, Agenten und Updates.",
        },
        "einstellungen_server": {
            "heading": "Server",
            "description": "Überblick über Server-Ressourcen, Dienste und Schnittstellenkonfigurationen.",
        },
        "einstellungen_allgemein": {
            "heading": "Allgemein",
            "description": "Globale Richtlinien, Benachrichtigungen und Integrationsoptionen des Test-Tools.",
        },
    }

    def _input_box_file_path(page_key: str, component_id: str) -> Path:
        relative = Path(page_key) / f"{component_id}.json"
        file_path = (DATA_DIR / relative).resolve()
        if not str(file_path).startswith(str(DATA_DIR.resolve())):
            raise ValueError("Ungültiger Speicherpfad")
        return file_path

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

    @app.context_processor
    def inject_input_box_helpers():
        return {
            "input_box_values": load_input_box_values,
        }

    def render_page(page_key: str, active_page: str):
        page = pages.get(page_key, {})
        return render_template(
            "page.html",
            title=page.get("heading", "WNGW"),
            heading=page.get("heading", ""),
            description=page.get("description", ""),
            active_page=active_page,
        )

    @app.route("/")
    def startseite():
        return render_page("startseite", "startseite")

    @app.route("/beobachten")
    def beobachten():
        return render_page("beobachten", "beobachten")

    @app.route("/pruefung/starten")
    def pruefung_starten():
        return render_page("pruefung_starten", "pruefung_starten")

    @app.route("/pruefung/konfigurieren")
    def pruefung_konfigurieren():
        return render_page("pruefung_konfigurieren", "pruefung_konfigurieren")

    @app.route("/pruefung/protokolle")
    def pruefprotokolle():
        return render_page("pruefprotokolle", "pruefung_protokolle")

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

    @app.route("/einstellungen/allgemein")
    def einstellungen_allgemein():
        return render_page("einstellungen_allgemein", "einstellungen_allgemein")

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

    @app.route("/components/<path:filename>")
    def component_asset(filename: str):
        return send_from_directory("frontend/components", filename)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

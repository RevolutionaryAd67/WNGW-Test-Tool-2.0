"""Entry point for the WNGW Test Tool Flask application."""
from __future__ import annotations

from flask import Flask, render_template

from backend.navigation import NavItem, build_sub_navigation, build_top_navigation

app = Flask(__name__, template_folder="frontend/templates", static_folder="frontend/static")

TOP_NAV = build_top_navigation()
SUB_NAV = build_sub_navigation()

BEOBACHTEN_SECTIONS = {
    "Client/Master": {
        "title": "Client/Master",
        "description": "Überblick über alle verbundenen Clients und Master-Instanzen.",
    },
    "Server/Slave": {
        "title": "Server/Slave",
        "description": "Status der Server- bzw. Slave-Dienste im Netzwerk.",
    },
    "Filter": {
        "title": "Filter",
        "description": "Definieren und verwalten Sie Filterregeln für Datenströme.",
    },
    "Optionen": {
        "title": "Optionen",
        "description": "Zusätzliche Beobachtungsoptionen und Einstellungen.",
    },
}


def _get_sub_nav(label: str) -> list[NavItem]:
    return SUB_NAV.get(label, [])


def _render_page(template: str, *, title: str, active_top: str, active_sub: str = "", **context):
    return render_template(
        template,
        title=title,
        top_nav=TOP_NAV,
        sub_nav=_get_sub_nav(active_top),
        active_top=active_top,
        active_sub=active_sub,
        **context,
    )


@app.route("/")
def index():
    return startseite()


@app.route("/startseite")
def startseite():
    return _render_page("startseite.html", title="Startseite", active_top="Startseite")


@app.route("/beobachten")
def beobachten():
    return beobachten_client_master()


@app.route("/beobachten/client-master")
def beobachten_client_master():
    return _render_beobachten_section("Client/Master")


@app.route("/beobachten/server-slave")
def beobachten_server_slave():
    return _render_beobachten_section("Server/Slave")


@app.route("/beobachten/filter")
def beobachten_filter():
    return _render_beobachten_section("Filter")


@app.route("/beobachten/optionen")
def beobachten_optionen():
    return _render_beobachten_section("Optionen")


def _render_beobachten_section(section_label: str):
    section = BEOBACHTEN_SECTIONS.get(section_label)
    if not section:
        section = {"title": section_label, "description": "Abschnitt nicht gefunden."}
    return _render_page(
        "beobachten.html",
        title=f"Beobachten - {section['title']}",
        active_top="Beobachten",
        active_sub=section_label,
        section_title=section["title"],
        section_description=section["description"],
    )


@app.route("/pruefung")
def pruefung():
    return _render_page("pruefung.html", title="Prüfung", active_top="Prüfung")


@app.route("/hilfe")
def hilfe():
    return _render_page("hilfe.html", title="Hilfe", active_top="Hilfe")


@app.route("/einstellungen")
def einstellungen():
    return _render_page("einstellungen.html", title="Einstellungen", active_top="Einstellungen")


if __name__ == "__main__":
    app.run(debug=True)

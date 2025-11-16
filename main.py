from flask import Flask, render_template


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="frontend/templates",
        static_folder="frontend/static",
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
            "heading": "Einstellungen – Client",
            "description": "Verwalten Sie clientseitige Parameter wie Benutzerrollen, Agenten und Updates.",
        },
        "einstellungen_server": {
            "heading": "Einstellungen – Server",
            "description": "Überblick über Server-Ressourcen, Dienste und Schnittstellenkonfigurationen.",
        },
        "einstellungen_allgemein": {
            "heading": "Einstellungen – Allgemein",
            "description": "Globale Richtlinien, Benachrichtigungen und Integrationsoptionen des Test-Tools.",
        },
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
        return render_page("einstellungen_client", "einstellungen_client")

    @app.route("/einstellungen/server")
    def einstellungen_server():
        return render_page("einstellungen_server", "einstellungen_server")

    @app.route("/einstellungen/allgemein")
    def einstellungen_allgemein():
        return render_page("einstellungen_allgemein", "einstellungen_allgemein")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

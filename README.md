# WNGW Test Tool 2.0

Dieses Projekt implementiert ein Prüf- und Beobachtungswerkzeug für IEC 60870-5-104.

## Projektstruktur

```
backend/    # FastAPI-Backend mit IEC-104-Platzhalter-Stacks
frontend/   # Statische Web-Oberfläche
data/       # Persistierte Konfigurationen, Signallisten und Logs
```

## Voraussetzungen

- Python 3.10+
- Abhängigkeiten aus `requirements.txt`

Installation:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Entwicklung

Backend starten:

```
uvicorn backend.app:app --reload
```

Das Frontend ist als statische Anwendung unter `frontend/` abgelegt und kann z. B. mit
`python -m http.server` bereitgestellt werden.

## Daten

- Konfigurationen liegen unter `data/configs/`
- Signallisten werden als JSON in `data/signals/` gespeichert
- Prüflogs werden in `data/logs/tests/` abgelegt

## Hinweise

Die IEC-104-Stacks sind als Platzhalter implementiert, um die vollständige Architektur,
WebSocket-Anbindung und das Prüfmodul demonstrieren zu können. Ein Austausch durch echte
Protokoll-Stacks ist aufgrund der modularen Struktur möglich.

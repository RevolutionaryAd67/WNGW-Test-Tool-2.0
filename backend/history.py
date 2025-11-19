#   Kommunikationsverlauf in JSON-Datei speichern
#
#   Aufgaben des Skripts
#       1. Verwaltet das Dateiverzeichnis, in dem Kommunikationsverläufe getrennt nach Client und Server gespeichert werden
#       2. Speichert neue Telegramme als JSON-Zeile in die entsprechende Datei
#       3. Lädt und bereinigt die Daten in den Dateien

from __future__ import annotations

import json
import threading
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional


# Funktionen, um Telegramme in JSON-Dateien zu speichern
class CommunicationHistory:
    
    # Erzeugt das Wurzelverzeichnis, falls es nicht existiert
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._valid_sides = {"client", "server"}

    # Jede Seite besitzt ihre eigene JSONL-Datei (client.jsonl und server.jsonl)
    def _file_for(self, side: str) -> Path:
        if side not in self._valid_sides:
            raise ValueError(f"Unknown history side: {side}")
        return self.base_dir / f"{side}.jsonl"

    # Nur Telegram-Ereignisse mit valider Seitenangabe werden akzeptiert
    def record(self, event: Dict) -> None:
        if not isinstance(event, dict) or event.get("type") != "telegram":
            return
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return
        side = payload.get("side")
        if side not in self._valid_sides:
            return
        file_path = self._file_for(side)
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    # Telegramme aus den JSON-Dateien lesen
    def load(self, side: str, limit: Optional[int] = None) -> List[Dict]:
        file_path = self._file_for(side)
        if not file_path.exists():
            return []
        entries: List[Dict] = []
        with self._lock:
            if limit is not None and limit > 0:
                buffer = deque(maxlen=limit)
                with file_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        buffer.append(line.rstrip("\n"))
                lines = list(buffer)
            else:
                lines = file_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    entries.append(payload)
            except json.JSONDecodeError:
                continue
        return entries

    # Telegramme aus den JSON-Dateien mit optionalem Limi zurückgeben
    def load_all(self, limit: Optional[int] = None) -> Dict[str, List[Dict]]:
        return {
            side: self.load(side, limit=limit)
            for side in sorted(self._valid_sides)
        }

    # Alle Telegramme aus einer JSON-Datei entfernen
    def clear(self, side: str) -> None:
        file_path = self._file_for(side)
        with self._lock:
            file_path.write_text("", encoding="utf-8")

"""Utilities for persisting and loading communication history."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List


class CommunicationHistory:
    """Store telegram payloads per side inside JSONL files."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._valid_sides = {"client", "server"}

    def _file_for(self, side: str) -> Path:
        if side not in self._valid_sides:
            raise ValueError(f"Unknown history side: {side}")
        return self.base_dir / f"{side}.jsonl"

    def record(self, event: Dict) -> None:
        """Persist a telegram event to the corresponding history file."""
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

    def load(self, side: str) -> List[Dict]:
        """Load the stored telegrams for a given side."""
        file_path = self._file_for(side)
        if not file_path.exists():
            return []
        entries: List[Dict] = []
        with self._lock:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    entries.append(payload)
            except json.JSONDecodeError:
                continue
        return entries

    def load_all(self) -> Dict[str, List[Dict]]:
        """Return the full history for all sides."""
        return {side: self.load(side) for side in sorted(self._valid_sides)}

    def clear(self, side: str) -> None:
        """Remove all entries for the given side."""
        file_path = self._file_for(side)
        with self._lock:
            file_path.write_text("", encoding="utf-8")


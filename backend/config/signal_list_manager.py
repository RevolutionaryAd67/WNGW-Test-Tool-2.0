"""Manage signal list files and mappings."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, List

from backend.utils.excel_parser import parse_signal_excel
from backend.utils.json_store import load_json, save_json

SIGNAL_ROOT = Path("data/signals")


class SignalListManager:
    """Handle storing and retrieving signal lists."""

    def __init__(self) -> None:
        SIGNAL_ROOT.mkdir(parents=True, exist_ok=True)

    def save_from_excel(self, excel_path: Path) -> Path:
        signals = parse_signal_excel(excel_path)
        target = SIGNAL_ROOT / f"{uuid.uuid4()}.json"
        save_json(target, {"signals": signals})
        return target

    def list_signals(self) -> List[Dict]:
        signal_files = sorted(SIGNAL_ROOT.glob("*.json"))
        payload: List[Dict] = []
        for file in signal_files:
            data = load_json(file, {"signals": []})
            payload.append({"file": str(file), "count": len(data.get("signals", []))})
        return payload


signal_list_manager = SignalListManager()

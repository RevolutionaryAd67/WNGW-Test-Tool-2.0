from __future__ import annotations

from typing import Any, Dict, List

from backend.utils.json_io import load_json, save_json
from backend.utils.paths import CONFIG_DIR, SIGNALS_DIR


class SettingsService:
    def __init__(self) -> None:
        self.config_dir = CONFIG_DIR
        self.signals_dir = SIGNALS_DIR

    def list_configs(self) -> List[str]:
        return sorted(f.name for f in self.config_dir.glob("*.json"))

    def load_config(self, name: str) -> Dict[str, Any]:
        data = load_json(self.config_dir / name)
        if data is None:
            raise FileNotFoundError(f"Config {name} not found")
        return data

    def save_config(self, name: str, data: Dict[str, Any]) -> None:
        save_json(self.config_dir / name, data)

    def list_signals(self) -> List[str]:
        return sorted(f.name for f in self.signals_dir.glob("*.json"))

    def load_signal_list(self, name: str) -> Dict[str, Any]:
        data = load_json(self.signals_dir / name)
        if data is None:
            raise FileNotFoundError(f"Signal list {name} not found")
        return data

    def save_signal_list(self, name: str, data: Dict[str, Any]) -> None:
        save_json(self.signals_dir / name, data)

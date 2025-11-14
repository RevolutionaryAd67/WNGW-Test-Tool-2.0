"""Manage persistent configuration for client and server."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal

from backend.utils.json_store import load_json, save_json

CONFIG_ROOT = Path("data/configs")
CLIENT_CONFIG = CONFIG_ROOT / "client_settings.json"
SERVER_CONFIG = CONFIG_ROOT / "server_settings.json"

_DEFAULT_CLIENT = {
    "partner": {"ip": "127.0.0.1", "ca": 1},
    "tcp": {"ip": "0.0.0.0", "port": 2404},
    "timers": {"t1": 15.0, "t2": 10.0, "t3": 20.0},
    "flow": {"k": 12, "w": 8},
}

_DEFAULT_SERVER = {
    "partner": {"ip": "127.0.0.1", "ca": 1},
    "tcp": {"ip": "0.0.0.0", "port": 2404},
    "asdu": {"ca": 1, "originator": 0},
    "timers": {"t1": 15.0, "t2": 10.0, "t3": 20.0},
    "flow": {"k": 12, "w": 8},
}


ConfigType = Literal["client", "server"]


class SettingsManager:
    """Load and save configuration files."""

    def __init__(self) -> None:
        CONFIG_ROOT.mkdir(parents=True, exist_ok=True)

    def load(self, config_type: ConfigType) -> Dict[str, Any]:
        if config_type == "client":
            return load_json(CLIENT_CONFIG, _DEFAULT_CLIENT)
        return load_json(SERVER_CONFIG, _DEFAULT_SERVER)

    def save(self, config_type: ConfigType, payload: Dict[str, Any]) -> Dict[str, Any]:
        if config_type == "client":
            save_json(CLIENT_CONFIG, payload)
        else:
            save_json(SERVER_CONFIG, payload)
        return payload


settings_manager = SettingsManager()

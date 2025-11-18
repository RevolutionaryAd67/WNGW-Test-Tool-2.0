"""Settings service handles configs and signal definitions."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from .logging_service import logging_service

SETTINGS_DIR = Path("data/settings")
CONFIG_FILE = SETTINGS_DIR / "configs.json"
SIGNALS_FILE = SETTINGS_DIR / "signals.json"

DEFAULT_CONFIGS: Dict[str, Any] = {
    "system": {
        "name": "IEC-104 Test Tool",
        "version": "2.0",
    },
    "client": {
        "communication_partner": {
            "ip": "127.0.0.1",
            "station_address": 1,
        },
        "tcp_connectivity": {
            "listen_ip": "0.0.0.0",
            "listen_port": 2404,
        },
    },
    "server": {
        "communication_partner": {
            "ip": "127.0.0.1",
            "station_address": 2,
        },
        "tcp_connectivity": {
            "listen_ip": "0.0.0.0",
            "listen_port": 2405,
        },
        "asdu_parameters": {
            "station_address": 100,
        },
    },
}


class SettingsService:
    def __init__(self) -> None:
        self._configs: Dict[str, Any] = deepcopy(DEFAULT_CONFIGS)
        self._signals: List[Dict[str, Any]] = []
        self._logger = logging_service.get_logger(__name__)

    def load(self) -> None:
        raw_configs = self._read_json(CONFIG_FILE, default=DEFAULT_CONFIGS)
        self._configs = self._merge_with_defaults(raw_configs)
        self._signals = self._read_json(SIGNALS_FILE, default=[])
        self._logger.info(
            "Settings loaded: %s configs keys, %s signals",
            len(self._configs),
            len(self._signals),
        )

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _merge_with_defaults(self, configs: Dict[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(DEFAULT_CONFIGS)
        self._deep_update(merged, configs)
        return merged

    def _deep_update(self, target: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
        return target

    def get_configs(self) -> Dict[str, Any]:
        return self._configs

    def save_configs(self, configs: Dict[str, Any]) -> Dict[str, Any]:
        self._configs = self._merge_with_defaults(configs)
        self._write_json(CONFIG_FILE, self._configs)
        self._logger.info("Settings configs saved")
        return self._configs

    def get_signals(self) -> List[Dict[str, Any]]:
        return self._signals

    def save_signals(self, signals: List[Dict[str, Any]]) -> None:
        self._signals = signals
        self._write_json(SIGNALS_FILE, signals)
        self._logger.info("Signals saved")

    def get_client_profile(self) -> Dict[str, Any]:
        client_cfg = self._configs.get("client", {})
        partner = client_cfg.get("communication_partner", {})
        tcp = client_cfg.get("tcp_connectivity", {})
        return {
            "partner_ip": partner.get("ip", DEFAULT_CONFIGS["client"]["communication_partner"]["ip"]),
            "partner_station": int(
                partner.get(
                    "station_address",
                    DEFAULT_CONFIGS["client"]["communication_partner"]["station_address"],
                )
            ),
            "listen_ip": tcp.get("listen_ip", DEFAULT_CONFIGS["client"]["tcp_connectivity"]["listen_ip"]),
            "listen_port": int(
                tcp.get("listen_port", DEFAULT_CONFIGS["client"]["tcp_connectivity"]["listen_port"])
            ),
        }

    def get_server_profile(self) -> Dict[str, Any]:
        server_cfg = self._configs.get("server", {})
        partner = server_cfg.get("communication_partner", {})
        tcp = server_cfg.get("tcp_connectivity", {})
        asdu = server_cfg.get("asdu_parameters", {})
        return {
            "partner_ip": partner.get("ip", DEFAULT_CONFIGS["server"]["communication_partner"]["ip"]),
            "partner_station": int(
                partner.get(
                    "station_address",
                    DEFAULT_CONFIGS["server"]["communication_partner"]["station_address"],
                )
            ),
            "listen_ip": tcp.get("listen_ip", DEFAULT_CONFIGS["server"]["tcp_connectivity"]["listen_ip"]),
            "listen_port": int(
                tcp.get("listen_port", DEFAULT_CONFIGS["server"]["tcp_connectivity"]["listen_port"])
            ),
            "station_address": int(
                asdu.get(
                    "station_address",
                    DEFAULT_CONFIGS["server"]["asdu_parameters"]["station_address"],
                )
            ),
        }


settings_service = SettingsService()

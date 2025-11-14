"""Persist test configurations and protocols."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, List

from backend.utils.json_store import load_json, save_json

CONFIG_PATH = Path("data/configs/test_configs.json")
LOG_ROOT = Path("data/logs/tests")

_DEFAULT_CONFIGS: List[dict] = []


class TestConfigsManager:
    """Manage CRUD operations for test configurations."""

    def __init__(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_ROOT.mkdir(parents=True, exist_ok=True)

    def list_configs(self) -> List[dict]:
        return load_json(CONFIG_PATH, _DEFAULT_CONFIGS)

    def save_config(self, payload: dict) -> dict:
        configs = self.list_configs()
        if not payload.get("id"):
            payload["id"] = str(uuid.uuid4())
            configs.append(payload)
        else:
            configs = [cfg if cfg["id"] != payload["id"] else payload for cfg in configs]
        save_json(CONFIG_PATH, configs)
        return payload

    def delete_config(self, config_id: str) -> None:
        configs = [cfg for cfg in self.list_configs() if cfg.get("id") != config_id]
        save_json(CONFIG_PATH, configs)

    def get_config(self, config_id: str) -> dict | None:
        for config in self.list_configs():
            if config.get("id") == config_id:
                return config
        return None


configs_manager = TestConfigsManager()

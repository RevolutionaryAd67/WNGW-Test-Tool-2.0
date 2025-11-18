"""Simple sequential test engine coordinating IEC-104 stacks."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_bus import EventBus
from .logging_service import TEST_LOG_DIR, logging_service
from backend.iec104.client_stack import client_stack
from backend.iec104.server_stack import server_stack

TEST_CONFIG_PATH = Path("data/tests/configs.json")


class TestEngine:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._logger = logging_service.get_logger(__name__)
        self._status: Dict[str, Any] = {"state": "idle"}
        self._active_task: Optional[asyncio.Task[Any]] = None
        self._tests = self._load_configs()
        TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_configs(self) -> List[Dict[str, Any]]:
        if not TEST_CONFIG_PATH.exists():
            return []
        with TEST_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_configs(self) -> List[Dict[str, Any]]:
        return self._tests

    def get_status(self) -> Dict[str, Any]:
        return self._status

    def get_logs(self) -> List[str]:
        if not TEST_LOG_DIR.exists():
            return []
        return sorted([p.name for p in TEST_LOG_DIR.iterdir() if p.is_dir()])

    def get_test_log_files(self, test_id: str) -> List[str]:
        directory = TEST_LOG_DIR / test_id
        if not directory.exists():
            return []
        return sorted([p.name for p in directory.glob("*.log")])

    def _update_status(self, **kwargs: Any) -> None:
        self._status.update(kwargs)

    def run(self, config_id: str) -> str:
        if self._active_task and not self._active_task.done():
            raise RuntimeError("A test is already running")
        config = next((cfg for cfg in self._tests if cfg["id"] == config_id), None)
        if not config:
            raise ValueError(f"Test config {config_id} not found")
        test_id = f"{config_id}-{uuid.uuid4().hex[:8]}"
        self._update_status(state="running", test_id=test_id, progress=0, name=config["name"])
        self._active_task = asyncio.create_task(self._execute(test_id, config))
        return test_id

    async def _execute(self, test_id: str, config: Dict[str, Any]) -> None:
        steps = int(config.get("steps", 1))
        directory = TEST_LOG_DIR / test_id
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / "execution.log"
        self._logger.info("Starting test %s", test_id)
        await self._event_bus.publish("tests", {"type": "start", "test_id": test_id, "name": config["name"]})
        try:
            for step in range(1, steps + 1):
                await asyncio.sleep(0.5)
                client_stack.simulate_network_activity()
                server_stack.simulate_packet()
                progress = int(step / steps * 100)
                self._update_status(progress=progress)
                await self._event_bus.publish("tests", {
                    "type": "progress",
                    "test_id": test_id,
                    "step": step,
                    "steps": steps,
                    "progress": progress,
                })
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"Step {step}/{steps} completed\n")
            self._update_status(state="completed", progress=100)
            await self._event_bus.publish("tests", {"type": "complete", "test_id": test_id})
        except Exception as exc:  # pylint: disable=broad-except
            self._logger.exception("Test %s failed", test_id)
            self._update_status(state="failed", error=str(exc))
            await self._event_bus.publish("tests", {"type": "error", "test_id": test_id, "error": str(exc)})
        finally:
            self._active_task = None

    def get_test_log_directory(self, test_id: str) -> Path:
        return TEST_LOG_DIR / test_id


_test_engine_instance: Optional[TestEngine] = None


def get_test_engine(event_bus: EventBus) -> TestEngine:
    global _test_engine_instance
    if _test_engine_instance is None:
        _test_engine_instance = TestEngine(event_bus)
    return _test_engine_instance

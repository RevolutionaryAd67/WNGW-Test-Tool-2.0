from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.iec104.client_stack import IEC104ClientStack
from backend.iec104.server_stack import IEC104ServerStack
from backend.services.event_bus import EventBus
from backend.services.logging_service import LoggingService
from backend.utils.json_io import load_json, save_json
from backend.utils.paths import CONFIG_DIR, TEST_LOG_DIR


class TestEngine:
    def __init__(
        self,
        event_bus: EventBus,
        client_stack: IEC104ClientStack,
        server_stack: IEC104ServerStack,
        logger: LoggingService,
    ) -> None:
        self.event_bus = event_bus
        self.client_stack = client_stack
        self.server_stack = server_stack
        self.logger = logger
        self._current_task: Optional[asyncio.Task] = None
        self._status: Dict[str, Any] = {
            "state": "idle",
            "current_test_id": None,
            "progress": 0,
            "details": None,
        }
        self._lock = asyncio.Lock()

    def list_test_configs(self) -> List[str]:
        return sorted(f.name for f in CONFIG_DIR.glob("test_*.json"))

    async def start_test(self, config_name: str) -> Dict[str, Any]:
        async with self._lock:
            if self._current_task and not self._current_task.done():
                raise RuntimeError("Another test is currently running")
            config_path = CONFIG_DIR / config_name
            config = load_json(config_path)
            if config is None:
                raise FileNotFoundError(f"Test config {config_name} not found")

            test_id = uuid.uuid4().hex
            self._status.update(
                {
                    "state": "running",
                    "current_test_id": test_id,
                    "progress": 0,
                    "details": {"config": config_name},
                }
            )
            self._current_task = asyncio.create_task(self._run_test(test_id, config))
            return self._status

    async def _run_test(self, test_id: str, config: Dict[str, Any]) -> None:
        log_dir = TEST_LOG_DIR / test_id
        log_dir.mkdir(parents=True, exist_ok=True)
        steps: List[Dict[str, Any]] = config.get("steps", [])
        total_steps = max(len(steps), 1)
        await self.event_bus.publish("tests", {"type": "started", "test_id": test_id})
        self.logger.info(f"Test {test_id} started with {len(steps)} steps")
        try:
            for index, step in enumerate(steps, start=1):
                await self._execute_step(test_id, index, step, log_dir)
                progress = int(index / total_steps * 100)
                self._status["progress"] = progress
                await self.event_bus.publish(
                    "tests",
                    {
                        "type": "progress",
                        "test_id": test_id,
                        "progress": progress,
                        "step": index,
                    },
                )
            await self._finalize_test(test_id, "passed", log_dir)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.error(f"Test {test_id} failed: {exc}")
            await self._finalize_test(test_id, "failed", log_dir, str(exc))

    async def _execute_step(
        self, test_id: str, index: int, step: Dict[str, Any], log_dir: Path
    ) -> None:
        action = step.get("action", "send")
        payload = step.get("payload", {"value": index})
        timestamp = time.time()
        if action == "send_client":
            frame = self.client_stack.send_asdu(payload)
        elif action == "send_server":
            frame = self.server_stack.send_asdu(payload)
        else:
            frame = {
                "action": action,
                "payload": payload,
            }
        record = {
            "step": index,
            "action": action,
            "payload": payload,
            "frame": frame,
            "timestamp": timestamp,
        }
        save_json(log_dir / f"step_{index}.json", record)
        await self.event_bus.publish(
            "tests",
            {"type": "step", "test_id": test_id, "step": index, "record": record},
        )

    async def _finalize_test(
        self, test_id: str, status: str, log_dir: Path, error: Optional[str] = None
    ) -> None:
        summary = {
            "test_id": test_id,
            "status": status,
            "error": error,
            "completed_at": time.time(),
        }
        save_json(log_dir / "summary.json", summary)
        self._status.update({"state": "idle", "progress": 100, "details": summary})
        await self.event_bus.publish("tests", {"type": "finished", **summary})
        self.logger.info(f"Test {test_id} finished with status {status}")

    def status(self) -> Dict[str, Any]:
        return self._status

    def list_logs(self) -> List[str]:
        return sorted(p.name for p in TEST_LOG_DIR.iterdir() if p.is_dir())

    def load_log(self, test_id: str) -> Dict[str, Any]:
        log_dir = TEST_LOG_DIR / test_id
        if not log_dir.exists():
            raise FileNotFoundError(f"Test log {test_id} not found")
        summary = load_json(log_dir / "summary.json") or {}
        steps = []
        for step_file in sorted(log_dir.glob("step_*.json")):
            steps.append(load_json(step_file))
        return {"summary": summary, "steps": steps}

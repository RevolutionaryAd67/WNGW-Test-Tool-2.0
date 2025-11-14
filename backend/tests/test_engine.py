"""Test execution engine."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import List

from backend.config.test_configs_manager import configs_manager
from backend.iec104.client_master import client_master
from backend.iec104.server_slave import server_slave
from backend.logging.log_formatter import export_log_lines
from backend.tests.test_models import TestRun, TestStep
from backend.utils.event_bus import event_bus
from backend.utils.file_utils import write_lines

TEST_CHANNEL = "tests"


class TestEngine:
    def __init__(self) -> None:
        self._current_run: TestRun | None = None
        self._lock = asyncio.Lock()

    async def start_run(self, config_id: str) -> TestRun:
        async with self._lock:
            if self._current_run is not None:
                raise RuntimeError("Another test run is active")
            config = configs_manager.get_config(config_id)
            if not config:
                raise ValueError("Configuration not found")
            run_id = str(uuid.uuid4())
            steps = [TestStep(**step, status="In Warteschlange") for step in config.get("steps", [])]
            self._current_run = TestRun(run_id=run_id, config_id=config_id, steps=steps, status="running")
            asyncio.create_task(self._execute_run(self._current_run))
            await event_bus.publish(TEST_CHANNEL, {"event": "run_started", "run_id": run_id})
            return self._current_run

    async def stop_run(self) -> None:
        async with self._lock:
            if self._current_run:
                self._current_run.status = "aborted"
                await event_bus.publish(TEST_CHANNEL, {"event": "run_aborted", "run_id": self._current_run.run_id})
                self._current_run = None

    async def _execute_run(self, run: TestRun) -> None:
        try:
            for step in run.steps:
                step.status = "Läuft"
                await self._notify_step(run, step)
                if step.type == "GA":
                    await self._run_gi_step(run, step)
                else:
                    step.status = "Fehlgeschlagen"
                    await self._notify_step(run, step)
                    break
                step.status = "Abgeschlossen"
                await self._notify_step(run, step)
            run.status = "finished"
            await self._notify_finished(run)
        except Exception as exc:  # pragma: no cover - runtime guard
            step.status = f"Fehlgeschlagen ({exc})"  # type: ignore
            run.status = "failed"
            await self._notify_step(run, step)
            await self._notify_error(run, str(exc))
        finally:
            async with self._lock:
                self._current_run = None

    async def _run_gi_step(self, run: TestRun, step: TestStep) -> None:
        if not client_master.state.active:
            raise RuntimeError("Client nicht aktiv")
        if not server_slave.state.active:
            raise RuntimeError("Server nicht aktiv")
        await client_master.send_general_interrogation()
        await asyncio.sleep(0.3)
        await server_slave.register_external_gi()
        await self._write_step_logs(run, step)

    async def _write_step_logs(self, run: TestRun, step: TestStep) -> None:
        run_path = Path("data/logs/tests") / run.run_id
        client_log = run_path / f"step_{step.index}_client.txt"
        server_log = run_path / f"step_{step.index}_server.txt"
        write_lines(client_log, export_log_lines(client_master.state.frames))
        write_lines(server_log, export_log_lines(server_slave.state.frames))

    async def _notify_step(self, run: TestRun, step: TestStep) -> None:
        await event_bus.publish(
            TEST_CHANNEL,
            {
                "event": "status_update",
                "run_id": run.run_id,
                "step": step.index,
                "status": step.status,
            },
        )

    async def _notify_finished(self, run: TestRun) -> None:
        await event_bus.publish(
            TEST_CHANNEL,
            {"event": "test_finished", "run_id": run.run_id, "status": run.status},
        )

    async def _notify_error(self, run: TestRun, message: str) -> None:
        await event_bus.publish(
            TEST_CHANNEL,
            {"event": "test_error", "run_id": run.run_id, "message": message},
        )


test_engine = TestEngine()

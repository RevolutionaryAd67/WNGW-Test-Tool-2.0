"""Routes for managing and executing tests."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.config.test_configs_manager import LOG_ROOT, configs_manager
from backend.tests import test_runner

router = APIRouter(prefix="/api/tests", tags=["tests"])


@router.get("/configs")
async def list_configs() -> dict:
    return {"configs": configs_manager.list_configs()}


@router.post("/configs")
async def create_config(payload: dict) -> dict:
    config = configs_manager.save_config(payload)
    return {"config": config}


@router.put("/configs/{config_id}")
async def update_config(config_id: str, payload: dict) -> dict:
    payload["id"] = config_id
    config = configs_manager.save_config(payload)
    return {"config": config}


@router.delete("/configs/{config_id}")
async def delete_config(config_id: str) -> dict:
    configs_manager.delete_config(config_id)
    return {"status": "deleted"}


@router.post("/run/{config_id}")
async def start_test_run(config_id: str) -> dict:
    try:
        run = await test_runner.start_test(config_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": run.run_id}


@router.post("/run/stop")
async def stop_test_run() -> dict:
    await test_runner.stop_test()
    return {"status": "stopped"}


@router.get("/logs")
async def list_test_logs() -> dict:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    entries = []
    for run_dir in LOG_ROOT.iterdir():
        if run_dir.is_dir():
            steps = sorted(run_dir.glob("step_*_client.txt"))
            entries.append(
                {
                    "run_id": run_dir.name,
                    "created": run_dir.stat().st_mtime,
                    "steps": [step.name for step in steps],
                }
            )
    return {"runs": entries}


@router.get("/logs/{run_id}/{filename}")
async def get_log_file(run_id: str, filename: str) -> str:
    target = LOG_ROOT / run_id / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Log not found")
    return target.read_text(encoding="utf-8")


@router.delete("/logs/{run_id}")
async def delete_log_run(run_id: str) -> dict:
    target = LOG_ROOT / run_id
    if target.exists() and target.is_dir():
        for file in target.glob("*"):
            file.unlink()
        target.rmdir()
    return {"status": "deleted"}

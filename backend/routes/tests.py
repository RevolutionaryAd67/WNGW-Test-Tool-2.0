from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services.system_context import get_event_bus
from backend.services.test_engine import get_test_engine

router = APIRouter(prefix="/tests", tags=["tests"])


def _engine():
    return get_test_engine(get_event_bus())


@router.get("/configs")
async def get_test_configs() -> list:
    return _engine().get_configs()


@router.post("/run")
async def run_test(payload: dict) -> dict:
    config_id = payload.get("config_id")
    if not config_id:
        raise HTTPException(status_code=400, detail="config_id is required")
    try:
        test_id = _engine().run(config_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"test_id": test_id}


@router.get("/status")
async def get_test_status() -> dict:
    return _engine().get_status()


@router.get("/logs")
async def get_test_logs() -> list:
    return _engine().get_logs()


@router.get("/logs/{test_id}")
async def get_test_log_files(test_id: str) -> list:
    return _engine().get_test_log_files(test_id)

from __future__ import annotations

from fastapi import APIRouter

from backend.services.settings_service import settings_service
from backend.services.stack_config_service import apply_stack_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/configs")
async def get_configs() -> dict:
    return settings_service.get_configs()


@router.post("/configs/save")
async def save_configs(payload: dict) -> dict:
    configs = settings_service.save_configs(payload)
    apply_stack_settings()
    return {"status": "saved", "configs": configs}


@router.get("/signals")
async def get_signals() -> list:
    return settings_service.get_signals()


@router.post("/signals/save")
async def save_signals(payload: list) -> dict:
    settings_service.save_signals(payload)
    return {"status": "saved"}

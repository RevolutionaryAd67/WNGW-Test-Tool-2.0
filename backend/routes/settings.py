from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


class ConfigSaveRequest(BaseModel):
    name: str
    data: dict


class SignalSaveRequest(BaseModel):
    name: str
    data: dict


def _service(request: Request) -> SettingsService:
    return request.app.state.settings_service


@router.get("/configs")
async def get_configs(request: Request) -> dict:
    service = _service(request)
    configs = [
        {"name": name, "content": service.load_config(name)}
        for name in service.list_configs()
    ]
    return {"configs": configs}


@router.post("/configs/save")
async def save_config(data: ConfigSaveRequest, request: Request) -> dict:
    service = _service(request)
    service.save_config(data.name, data.data)
    return {"saved": data.name}


@router.get("/signals")
async def get_signals(request: Request) -> dict:
    service = _service(request)
    signals = [
        {"name": name, "content": service.load_signal_list(name)}
        for name in service.list_signals()
    ]
    return {"signals": signals}


@router.post("/signals/save")
async def save_signals(data: SignalSaveRequest, request: Request) -> dict:
    service = _service(request)
    service.save_signal_list(data.name, data.data)
    return {"saved": data.name}

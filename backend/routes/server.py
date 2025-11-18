from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.iec104.server_stack import IEC104ServerStack
from backend.services.frontend_settings_service import FrontendSettingsService

router = APIRouter(prefix="/server", tags=["server"])


class SendRequest(BaseModel):
    payload: dict


def _stack(request: Request) -> IEC104ServerStack:
    return request.app.state.server_stack


def _frontend_settings(request: Request) -> FrontendSettingsService:
    return request.app.state.frontend_settings


@router.post("/start")
async def start_server(request: Request) -> dict:
    profile = _frontend_settings(request).load_server_profile()
    stack = _stack(request)
    stack.apply_connection_profile(profile)
    status = stack.start()
    await request.app.state.event_bus.publish("server", {"type": "status", **status})
    return status


@router.post("/stop")
async def stop_server(request: Request) -> dict:
    status = _stack(request).stop()
    await request.app.state.event_bus.publish("server", {"type": "status", **status})
    return status


@router.post("/send")
async def send_server_frame(data: SendRequest, request: Request) -> dict:
    try:
        frame = _stack(request).send_asdu(data.payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await request.app.state.event_bus.publish("server", {"type": "sent", "frame": frame})
    return frame


@router.get("/status")
async def server_status(request: Request) -> dict:
    return _stack(request).status()

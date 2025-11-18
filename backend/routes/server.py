from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.iec104.server_stack import server_stack
from backend.services.system_context import get_event_bus

router = APIRouter(prefix="/server", tags=["server"])


@router.post("/start")
async def start_server() -> dict:
    await server_stack.start()
    await get_event_bus().publish("server", {"type": "started", "status": server_stack.status()})
    return {"status": server_stack.status()}


@router.post("/stop")
async def stop_server() -> dict:
    await server_stack.stop()
    await get_event_bus().publish("server", {"type": "stopped", "status": server_stack.status()})
    return {"status": server_stack.status()}


@router.post("/send")
async def send_server(payload: dict) -> dict:
    try:
        response = await server_stack.send_asdu(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await get_event_bus().publish("server", {"type": "send", "payload": payload, "response": response})
    return response


@router.get("/status")
async def server_status() -> dict:
    return server_stack.status()

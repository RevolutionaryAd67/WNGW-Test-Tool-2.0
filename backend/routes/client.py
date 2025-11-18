from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.iec104.client_stack import client_stack
from backend.services.system_context import get_event_bus

router = APIRouter(prefix="/client", tags=["client"])


@router.post("/start")
async def start_client() -> dict:
    await client_stack.start()
    await get_event_bus().publish("client", {"type": "started", "status": client_stack.status()})
    return {"status": client_stack.status()}


@router.post("/stop")
async def stop_client() -> dict:
    await client_stack.stop()
    await get_event_bus().publish("client", {"type": "stopped", "status": client_stack.status()})
    return {"status": client_stack.status()}


@router.post("/send")
async def send_client(payload: dict) -> dict:
    try:
        response = await client_stack.send_asdu(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await get_event_bus().publish("client", {"type": "send", "payload": payload, "response": response})
    return response


@router.get("/status")
async def client_status() -> dict:
    return client_stack.status()

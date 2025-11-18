from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.iec104.client_stack import client_stack
from backend.iec104.server_stack import server_stack
from backend.services.system_context import get_event_bus

router = APIRouter(tags=["websocket"])


async def _stream_channel(websocket: WebSocket, channel: str, initial_payload: Optional[dict] = None) -> None:
    await websocket.accept()
    queue = await get_event_bus().get_queue(channel)
    try:
        if initial_payload is not None:
            await websocket.send_json(initial_payload)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        await get_event_bus().unsubscribe(channel, queue)


@router.websocket("/ws/client")
async def client_ws(websocket: WebSocket) -> None:
    await _stream_channel(websocket, "client", {"type": "status", "status": client_stack.status()})


@router.websocket("/ws/server")
async def server_ws(websocket: WebSocket) -> None:
    await _stream_channel(websocket, "server", {"type": "status", "status": server_stack.status()})


@router.websocket("/ws/system")
async def system_ws(websocket: WebSocket) -> None:
    await _stream_channel(websocket, "system")


@router.websocket("/ws/tests")
async def tests_ws(websocket: WebSocket) -> None:
    await _stream_channel(websocket, "tests")

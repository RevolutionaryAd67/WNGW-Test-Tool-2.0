"""WebSocket endpoints for live updates."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.utils.event_bus import event_bus

router = APIRouter()


async def _forward_events(websocket: WebSocket, channel: str) -> None:
    async with event_bus.subscribe(channel) as queue:
        while True:
            message = await queue.get()
            await websocket.send_json(message)


@router.websocket("/ws/client")
async def websocket_client(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _forward_events(websocket, "client")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/server")
async def websocket_server(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _forward_events(websocket, "server")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/tests")
async def websocket_tests(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _forward_events(websocket, "tests")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/system")
async def websocket_system(websocket: WebSocket) -> None:
    await websocket.accept()
    async def system_clock() -> None:
        while True:
            await asyncio.sleep(1)
            await websocket.send_json(
                {
                    "event": "clock",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

    clock_task = asyncio.create_task(system_clock())
    try:
        await _forward_events(websocket, "system")
    except WebSocketDisconnect:
        clock_task.cancel()
        return

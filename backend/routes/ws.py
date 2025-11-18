from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


async def _event_stream(websocket: WebSocket, channel: str) -> None:
    event_bus = websocket.app.state.event_bus
    await websocket.accept()
    async for message in event_bus.subscribe(channel):
        await websocket.send_json(message)


@router.websocket("/ws/client")
async def client_ws(websocket: WebSocket) -> None:
    try:
        await _event_stream(websocket, "client")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/server")
async def server_ws(websocket: WebSocket) -> None:
    try:
        await _event_stream(websocket, "server")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/system")
async def system_ws(websocket: WebSocket) -> None:
    try:
        await _event_stream(websocket, "system")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/tests")
async def tests_ws(websocket: WebSocket) -> None:
    try:
        await _event_stream(websocket, "tests")
    except WebSocketDisconnect:
        return

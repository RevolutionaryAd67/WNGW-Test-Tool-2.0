"""API routes for the IEC-104 server/slave."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.iec104.server_slave import server_slave

router = APIRouter(prefix="/api/server", tags=["server"])


@router.post("/start")
async def start_server() -> dict:
    await server_slave.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_server() -> dict:
    await server_slave.stop()
    return {"status": "stopped"}


@router.post("/simulate-gi")
async def simulate_gi() -> dict:
    try:
        await server_slave.register_external_gi()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "processed"}


@router.post("/clear")
async def clear_server_log() -> dict:
    server_slave.clear_log()
    return {"status": "cleared"}


@router.post("/export")
async def export_server_log() -> dict:
    target = Path("data/logs/exports") / "server_log.txt"
    server_slave.export_log(target)
    return {"status": "exported", "path": str(target)}

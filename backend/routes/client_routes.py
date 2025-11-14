"""API routes for the IEC-104 client/master."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.iec104.client_master import client_master

router = APIRouter(prefix="/api/client", tags=["client"])


@router.post("/start")
async def start_client() -> dict:
    await client_master.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_client() -> dict:
    await client_master.stop()
    return {"status": "stopped"}


@router.post("/gi")
async def trigger_general_interrogation() -> dict:
    try:
        frame = await client_master.send_general_interrogation()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "sent", "frame": frame}


@router.post("/clear")
async def clear_client_log() -> dict:
    client_master.clear_log()
    return {"status": "cleared"}


@router.post("/export")
async def export_client_log() -> dict:
    target = Path("data/logs/exports") / "client_log.txt"
    client_master.export_log(target)
    return {"status": "exported", "path": str(target)}

"""Routes for exporting combined logs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from backend.iec104.client_master import client_master
from backend.iec104.server_slave import server_slave

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.post("/export")
async def export_logs() -> dict:
    export_dir = Path("data/logs/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    client_path = export_dir / "client_log.txt"
    server_path = export_dir / "server_log.txt"
    client_master.export_log(client_path)
    server_slave.export_log(server_path)
    return {"client": str(client_path), "server": str(server_path)}

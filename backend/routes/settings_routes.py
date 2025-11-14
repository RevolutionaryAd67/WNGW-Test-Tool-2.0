"""Settings endpoints for client and server configuration."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from backend.config.settings_manager import settings_manager
from backend.config.signal_list_manager import signal_list_manager

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/client")
async def get_client_settings() -> dict:
    return settings_manager.load("client")


@router.post("/client")
async def save_client_settings(payload: dict) -> dict:
    result = settings_manager.save("client", payload)
    from backend.iec104.client_master import client_master  # lazy import to avoid cycles

    client_master.reload_settings()
    return result


@router.get("/server")
async def get_server_settings() -> dict:
    return settings_manager.load("server")


@router.post("/server")
async def save_server_settings(payload: dict) -> dict:
    result = settings_manager.save("server", payload)
    from backend.iec104.server_slave import server_slave  # lazy import to avoid cycles

    server_slave.reload_settings()
    return result


@router.get("/signals")
async def list_signals() -> dict:
    return {"signals": signal_list_manager.list_signals()}


@router.post("/signals/upload")
async def upload_signal_list(file: UploadFile = File(...)) -> dict:
    temp_path = Path("data/tmp") / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    temp_path.write_bytes(content)
    stored = signal_list_manager.save_from_excel(temp_path)
    temp_path.unlink(missing_ok=True)
    return {"status": "uploaded", "path": str(stored)}

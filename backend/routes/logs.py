from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.utils.paths import TEST_LOG_DIR

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/tests")
async def list_log_files() -> dict:
    logs = []
    for test_dir in sorted(TEST_LOG_DIR.iterdir()):
        if not test_dir.is_dir():
            continue
        files = [file.name for file in test_dir.glob("*.json")]
        logs.append({"test_id": test_dir.name, "files": files})
    return {"logs": logs}


@router.get("/tests/{filename}")
async def download_log(filename: str) -> FileResponse:
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = TEST_LOG_DIR / filename
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Filename must reference a file")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(target)

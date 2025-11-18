from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.services.logging_service import TEST_LOG_DIR

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/tests")
async def list_test_logs() -> list:
    if not TEST_LOG_DIR.exists():
        return []
    return sorted(str(path.relative_to(TEST_LOG_DIR)) for path in TEST_LOG_DIR.rglob("*.log"))


@router.get("/tests/{file_path:path}")
async def download_test_log(file_path: str):
    file_path = TEST_LOG_DIR / file_path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(file_path)

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.services.test_engine import TestEngine

router = APIRouter(prefix="/tests", tags=["tests"])


class RunTestRequest(BaseModel):
    config: str


def _engine(request: Request) -> TestEngine:
    return request.app.state.test_engine


@router.get("/configs")
async def list_test_configs(request: Request) -> dict:
    return {"configs": _engine(request).list_test_configs()}


@router.post("/run")
async def run_test(data: RunTestRequest, request: Request) -> dict:
    try:
        status = await _engine(request).start_test(data.config)
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return status


@router.get("/status")
async def test_status(request: Request) -> dict:
    return _engine(request).status()


@router.get("/logs")
async def list_test_logs(request: Request) -> dict:
    return {"logs": _engine(request).list_logs()}


@router.get("/logs/{test_id}")
async def get_test_log(test_id: str, request: Request) -> dict:
    try:
        log = _engine(request).load_log(test_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return log

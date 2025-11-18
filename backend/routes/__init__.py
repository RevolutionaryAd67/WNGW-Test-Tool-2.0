"""Router registration helpers."""
from __future__ import annotations

from fastapi import APIRouter

from .client import router as client_router
from .server import router as server_router
from .settings import router as settings_router
from .tests import router as tests_router
from .logs import router as logs_router
from .websockets import router as websocket_router


def get_routers() -> list[APIRouter]:
    return [
        client_router,
        server_router,
        settings_router,
        tests_router,
        logs_router,
        websocket_router,
    ]

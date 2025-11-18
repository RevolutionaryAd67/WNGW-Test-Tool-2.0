from __future__ import annotations

from .client import router as client_router
from .logs import router as logs_router
from .server import router as server_router
from .settings import router as settings_router
from .tests import router as tests_router
from .ws import router as ws_router

api_routers = [client_router, server_router, settings_router, tests_router, logs_router]
websocket_router = ws_router

from __future__ import annotations

import asyncio
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.iec104.client_stack import IEC104ClientStack
from backend.iec104.server_stack import IEC104ServerStack
from backend.routes import api_routers, websocket_router
from backend.services.event_bus import EventBus
from backend.services.frontend_settings_service import FrontendSettingsService
from backend.services.logging_service import LoggingService
from backend.services.settings_service import SettingsService
from backend.services.test_engine import TestEngine

app = FastAPI(title="IEC 104 Test Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = LoggingService()
event_bus = EventBus()
settings_service = SettingsService()
client_stack = IEC104ClientStack()
server_stack = IEC104ServerStack()
test_engine = TestEngine(event_bus, client_stack, server_stack, logger)
frontend_settings = FrontendSettingsService()

app.state.logger = logger
app.state.event_bus = event_bus
app.state.settings_service = settings_service
app.state.client_stack = client_stack
app.state.server_stack = server_stack
app.state.test_engine = test_engine
app.state.system_configs: Dict[str, dict] = {}
app.state.frontend_settings = frontend_settings


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Backend startup initiated")
    configs: Dict[str, dict] = {}
    loop = asyncio.get_running_loop()
    client_stack.register_event_bus(event_bus, loop, "client")
    server_stack.register_event_bus(event_bus, loop, "server")
    for name in settings_service.list_configs():
        try:
            configs[name] = settings_service.load_config(name)
        except FileNotFoundError:
            continue
    app.state.system_configs = configs
    await event_bus.publish(
        "system",
        {"type": "startup", "message": "Backend ready", "configs": list(configs.keys())},
    )


for router in api_routers:
    app.include_router(router)

app.include_router(websocket_router)

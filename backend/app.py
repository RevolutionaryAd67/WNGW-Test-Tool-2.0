"""FastAPI application entry point for the IEC-104 test backend."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import get_routers
from backend.services.event_bus import EventBus
from backend.services.logging_service import logging_service
from backend.services.settings_service import settings_service
from backend.services.stack_config_service import apply_stack_settings
from backend.services.system_context import set_event_bus
from backend.services.test_engine import get_test_engine

app = FastAPI(title="IEC-104 Test Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

event_bus = EventBus()
set_event_bus(event_bus)

for router in get_routers():
    app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    logging_service.configure()
    settings_service.load()
    apply_stack_settings()
    get_test_engine(event_bus)
    await event_bus.publish("system", {"type": "startup", "message": "Backend initialized"})


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await event_bus.publish("system", {"type": "shutdown", "message": "Backend stopping"})

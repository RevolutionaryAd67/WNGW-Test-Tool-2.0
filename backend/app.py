"""Main FastAPI application entry point for the WNGW Test Tool."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.logging.logger import configure_logging
from backend.routes import client_routes, logs_routes, server_routes, settings_routes, tests_routes, websocket
from backend.utils.event_bus import event_bus

APP_TITLE = "WNGW-Test-Tool"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=APP_TITLE)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(client_routes.router)
    app.include_router(server_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(tests_routes.router)
    app.include_router(logs_routes.router)
    app.include_router(websocket.router)

    @app.on_event("startup")
    async def on_startup() -> None:  # pragma: no cover - executed by ASGI server
        configure_logging()
        Path("data").mkdir(parents=True, exist_ok=True)
        await event_bus.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:  # pragma: no cover - executed by ASGI server
        await event_bus.stop()

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual startup helper
    import uvicorn

    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)

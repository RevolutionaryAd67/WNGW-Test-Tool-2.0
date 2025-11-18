"""Application wide logging helpers."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


LOG_DIR = Path("data/logs")
TEST_LOG_DIR = LOG_DIR / "tests"


class LoggingService:
    """Central logging configuration helper."""

    def __init__(self) -> None:
        self._configured = False

    def configure(self) -> None:
        if self._configured:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(LOG_DIR / "backend.log"),
            ],
        )
        self._configured = True

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        self.configure()
        return logging.getLogger(name)


logging_service = LoggingService()

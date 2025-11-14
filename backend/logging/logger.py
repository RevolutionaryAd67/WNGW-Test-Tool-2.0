"""Logging helpers for the WNGW Test Tool."""
from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE = Path("data/logs/system.log")


def configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

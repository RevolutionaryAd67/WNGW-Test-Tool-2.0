from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from backend.utils.paths import DATA_DIR


class LoggingService:
    def __init__(self, logfile: Optional[Path] = None) -> None:
        log_path = logfile or DATA_DIR / "logs" / "system.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
        )
        self.logger = logging.getLogger("iec104-backend")

    def info(self, message: str) -> None:
        self.logger.info(message)

    def error(self, message: str) -> None:
        self.logger.error(message)

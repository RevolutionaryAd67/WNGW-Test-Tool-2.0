from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = DATA_DIR / "configs"
SIGNALS_DIR = DATA_DIR / "signals"
TEST_LOG_DIR = DATA_DIR / "logs" / "tests"
CLIENT_SETTINGS_DIR = DATA_DIR / "einstellungen_client"
SERVER_SETTINGS_DIR = DATA_DIR / "einstellungen_server"

for directory in (
    DATA_DIR,
    CONFIG_DIR,
    SIGNALS_DIR,
    TEST_LOG_DIR,
    CLIENT_SETTINGS_DIR,
    SERVER_SETTINGS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

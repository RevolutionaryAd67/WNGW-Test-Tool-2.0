"""Public interface for triggering test runs."""
from __future__ import annotations

from backend.tests.test_engine import test_engine


async def start_test(config_id: str):
    return await test_engine.start_run(config_id)


async def stop_test():
    await test_engine.stop_run()

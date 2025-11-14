"""Data models for the testing subsystem."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TestStep:
    index: int
    type: str
    signal_list: str | None = None
    status: str = ""


@dataclass
class TestRun:
    run_id: str
    config_id: str
    steps: List[TestStep] = field(default_factory=list)
    status: str = "pending"

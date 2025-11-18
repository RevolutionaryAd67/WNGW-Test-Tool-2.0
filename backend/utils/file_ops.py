"""Utility helpers for dealing with files and directories."""
from __future__ import annotations

from pathlib import Path
from typing import List


def list_files(directory: Path, pattern: str = "*") -> List[str]:
    if not directory.exists():
        return []
    return sorted(str(path.name) for path in directory.glob(pattern) if path.is_file())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

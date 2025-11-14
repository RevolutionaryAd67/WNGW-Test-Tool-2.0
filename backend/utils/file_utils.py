"""General file helper functions."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_lines(path: Path, lines: Iterable[str]) -> None:
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8") as file:
        for line in lines:
            file.write(f"{line}\n")

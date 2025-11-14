"""Decode raw bytes into simplified frame dictionaries.

This module currently provides placeholder behaviour that mimics IEC-104
processing so the remainder of the tool can operate without a physical
connection. The structure mirrors the real decoder so later the actual
protocol implementation can be dropped in without touching other modules.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict


def decode_placeholder(payload: Dict) -> Dict:
    """Return the payload enriched with standard metadata."""
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    payload.setdefault("frame_format", "I")
    payload.setdefault("direction", "in")
    return payload

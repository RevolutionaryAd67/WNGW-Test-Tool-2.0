"""Encode IEC-104 frames into structured dictionaries."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List


GI_TYPE_ID = 100
COT_ACTIVATION = 6
COT_CONFIRMATION = 7
COT_TERMINATION = 10


def build_gi_frame(sequence: int, direction: str, ca: int, description: str, cot: int) -> Dict:
    now = datetime.utcnow().isoformat()
    return {
        "sequence": sequence,
        "direction": direction,
        "timestamp": now,
        "frame_format": "I",
        "type_id": GI_TYPE_ID,
        "cot_byte1": cot,
        "cot_byte2": 11,
        "ca": ca,
        "ioa": [0, 0, 0],
        "src_ip": "0.0.0.0",
        "src_port": 2404,
        "dst_ip": "0.0.0.0",
        "dst_port": 2404,
        "description": description,
    }


def build_u_frame(sequence: int, direction: str, description: str) -> Dict:
    now = datetime.utcnow().isoformat()
    return {
        "sequence": sequence,
        "direction": direction,
        "timestamp": now,
        "frame_format": "U",
        "description": description,
        "src_ip": "0.0.0.0",
        "src_port": 2404,
        "dst_ip": "0.0.0.0",
        "dst_port": 2404,
    }


def build_s_frame(sequence: int, direction: str, description: str) -> Dict:
    now = datetime.utcnow().isoformat()
    return {
        "sequence": sequence,
        "direction": direction,
        "timestamp": now,
        "frame_format": "S",
        "description": description,
        "src_ip": "0.0.0.0",
        "src_port": 2404,
        "dst_ip": "0.0.0.0",
        "dst_port": 2404,
    }

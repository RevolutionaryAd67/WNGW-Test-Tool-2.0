"""Helpers for formatting IEC-104 log messages."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List


def format_frame_for_display(frame: Dict) -> str:
    """Format a telemetry frame for UI display."""
    timestamp = _format_timestamp(frame.get("timestamp"))
    direction_color = "blue" if frame.get("direction") == "out" else "black"
    header = f"{frame.get('sequence', 0):>4} : {frame.get('description', 'UNKNOWN')}"
    ip_line = (
        f"IP:Port       : {frame.get('src_ip', '-')}:" f"{frame.get('src_port', '-')}">
        f" --> {frame.get('dst_ip', '-')}:" f"{frame.get('dst_port', '-')}"
    )
    if frame.get("frame_format") == "I":
        type_line = f"Typ           : {frame.get('type_id', '-') } (I-Format)"
        cause_line = (
            "Ursache       : "
            f"Aktivierung = {frame.get('cot_byte1', '-'):<3}    "
            f"Herkunft = {frame.get('cot_byte2', '-'):<3}"
        )
        ca_line = f"Station       : {frame.get('ca', '-')}"
        ioa = frame.get("ioa", [0, 0, 0])
        ioa_line = f"IOA           : {ioa[0]}- {ioa[1]}- {ioa[2]}"
        body = "\n".join([timestamp, ip_line, type_line, cause_line, ca_line, ioa_line])
    else:
        type_line = f"Typ          : ({frame.get('frame_format', 'U')}-Format)"
        body = "\n".join([timestamp, ip_line, type_line])
    return f"{header}\n{body}", direction_color


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "Zeit         : -"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return f"Zeit         : {value}"
    return f"Zeit         : {dt.strftime('%H:%M:%S.%f')[:-3]}"


def export_log_lines(frames: Iterable[Dict]) -> List[str]:
    lines: List[str] = []
    for frame in frames:
        formatted, _ = format_frame_for_display(frame)
        lines.append(formatted)
        lines.append("")
    return lines

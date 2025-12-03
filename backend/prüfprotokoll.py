from __future__ import annotations

import io
import time
import zipfile
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape


def format_timestamp_text(value: Any) -> str:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return "-"
    millis = int(round((ts - int(ts)) * 1000))
    if millis == 1000:
        ts += 0.001
        millis = 0
    formatted = time.strftime("%H:%M:%S", time.localtime(ts))
    return f"{formatted}.{millis:03d}"


def _determine_direction_arrow(entry: Dict[str, Any]) -> str:
    side = str(entry.get("side") or "").lower()
    direction = str(entry.get("direction") or "").lower()
    if side not in ("client", "server"):
        return ""
    source = side if direction == "outgoing" else ("server" if side == "client" else "client")
    if source == "client":
        return ">"
    if source == "server":
        return "<"
    return ""


def _format_qualifier_bits(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        parsed = int(str(value), 0) & 0xFF
    except (TypeError, ValueError):
        return str(value) if value not in (None, "") else ""
    return format(parsed, "08b")


def _build_excel_row_from_telegram(entry: Dict[str, Any]) -> Optional[Dict[int, Any]]:
    side = entry.get("side")
    if side not in ("client", "server"):
        return None
    ioa = entry.get("ioa")
    if not isinstance(ioa, int):
        return None

    meldetext = entry.get("meldetext") or entry.get("label") or ""
    timestamp_text = format_timestamp_text(entry.get("timestamp"))
    qualifier_bits = _format_qualifier_bits(entry.get("qualifier"))
    direction_arrow = _determine_direction_arrow(entry)
    base_row: Dict[int, Any] = {15: direction_arrow}

    if side == "client":
        base_row.update(
            {
                6: timestamp_text,  # F: Zeit (Client)
                7: meldetext,  # G: Meldetext (Client)
                8: str(ioa),  # H: IOAs (Client)
                9: entry.get("type_id"),  # I: TK (Client)
                10: entry.get("cause"),  # J: COT (Client)
                11: entry.get("originator"),  # K: HK (Client)
                12: entry.get("station"),  # L: CA (Client)
                13: entry.get("value"),  # M: Wert (Client)
                14: qualifier_bits,  # N: Qualifier (Client)
            }
        )
    else:
        base_row.update(
            {
                16: timestamp_text,  # P: Zeit (Server)
                17: meldetext,  # Q: Meldetext (Server)
                18: str(ioa),  # R: IOAs (Server)
                19: entry.get("type_id"),  # S: TK (Server)
                20: entry.get("cause"),  # T: COT (Server)
                21: entry.get("originator"),  # U: HK (Server)
                22: entry.get("station"),  # V: CA (Server)
                23: entry.get("value"),  # W: Wert (Server)
                24: qualifier_bits,  # X: Qualifier (Server)
            }
        )

    return base_row


def _build_excel_rows_from_communication(
    telegram_entries: List[Dict[str, Any]]
) -> List[Dict[int, Any]]:
    def _timestamp_key(entry: Dict[str, Any]) -> float:
        try:
            return float(entry.get("timestamp", 0.0))
        except (TypeError, ValueError):
            return 0.0

    sorted_entries = sorted(
        (entry for entry in telegram_entries if isinstance(entry, dict)),
        key=_timestamp_key,
    )

    rows: List[Dict[int, Any]] = []
    for entry in sorted_entries:
        ioa = entry.get("ioa")
        if not isinstance(ioa, int):
            continue
        row = _build_excel_row_from_telegram(entry)
        if row:
            rows.append(row)
    return rows


def _column_letter(index: int) -> str:
    if index <= 0:
        return ""
    letters: List[str] = []
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _inline_string_cell(column_index: int, row_index: int, value: str) -> str:
    if value is None:
        value = ""
    text = escape(str(value))
    cell_ref = f"{_column_letter(column_index)}{row_index}"
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _create_excel_workbook(headers: List[str], rows: List[Dict[int, str]]) -> bytes:
    header_row_index = 3
    first_data_row_index = header_row_index + 1
    last_row_index = max(header_row_index, first_data_row_index + len(rows) - 1)
    last_column_index = len(headers)
    dimension = f"A{header_row_index}:{_column_letter(last_column_index)}{last_row_index}"

    header_cells = [
        _inline_string_cell(index + 1, header_row_index, header)
        for index, header in enumerate(headers)
    ]

    data_rows: List[str] = []
    for offset, row in enumerate(rows):
        row_index = first_data_row_index + offset
        cells = [
            _inline_string_cell(col_index, row_index, value)
            for col_index, value in sorted(row.items())
            if value not in (None, "")
        ]
        if cells:
            data_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        else:
            data_rows.append(f'<row r="{row_index}"/>')

    sheet_rows = "".join([f'<row r="{header_row_index}">{"".join(header_cells)}</row>'] + data_rows)
    sheet_content = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        f"xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<dimension ref=\"{dimension}\"/>"
        f"<sheetData>{sheet_rows}</sheetData>"
        "</worksheet>"
    )

    workbook_content = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        "<sheets>"
        "<sheet name=\"Prüfprotokoll\" sheetId=\"1\" r:id=\"rId1\"/>"
        "</sheets>"
        "</workbook>"
    )

    workbook_rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>"
        "</Relationships>"
    )

    root_rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "</Relationships>"
    )

    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "</Types>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_content)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_content)
    return buffer.getvalue()


def build_protocol_excel(telegram_entries: Optional[List[Dict[str, Any]]] = None) -> bytes:
    headers = [
        "Meldetext",
        "IOAs",
        "TK",
        "COT",
        "HK",
        "Zeit",
        "Meldetext",
        "IOAs",
        "TK",
        "COT",
        "HK",
        "CA",
        "Wert",
        "Qualifier",
        "Richtung",
        "Zeit",
        "Meldetext",
        "IOAs",
        "TK",
        "COT",
        "HK",
        "CA",
        "Wert",
        "Qualifier",
    ]
    rows = _build_excel_rows_from_communication(telegram_entries or [])
    return _create_excel_workbook(headers, rows)

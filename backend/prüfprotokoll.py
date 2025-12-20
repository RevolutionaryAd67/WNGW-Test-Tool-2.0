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


def _parse_timestamp_value(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_match_value(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _styled_cell(value: Any, style: str) -> Dict[str, Any]:
    return {"value": value, "style": style}


def _build_excel_rows_from_communication(
    telegram_entries: List[Dict[str, Any]]
) -> tuple[List[Dict[int, Any]], List[Dict[str, Any]]]:
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
    metadata: List[Dict[str, Any]] = []
    for entry in sorted_entries:
        ioa = entry.get("ioa")
        if not isinstance(ioa, int):
            continue
        row = _build_excel_row_from_telegram(entry)
        if row:
            rows.append(row)
            metadata.append(
                {
                    "side": entry.get("side"),
                    "ioa": _normalize_match_value(ioa),
                    "cot": _normalize_match_value(entry.get("cause")),
                    "timestamp": _parse_timestamp_value(entry.get("timestamp")),
                    "direction": _determine_direction_arrow(entry),
                }
            )
    return rows, metadata


def _find_matching_row_indices(
    metadata: List[Dict[str, Any]],
    max_wait_seconds: float,
) -> Dict[int, int]:
    matches: Dict[int, int] = {}
    for index, row_meta in enumerate(metadata):
        side = row_meta.get("side")
        if side not in ("client", "server"):
            continue
        direction = row_meta.get("direction")
        ioa = row_meta.get("ioa")
        cot = row_meta.get("cot")
        current_time = row_meta.get("timestamp")
        if ioa is None or cot is None or current_time is None:
            continue
        target_side = "server" if side == "client" else "client"
        latest_time = current_time + max_wait_seconds
        search_backward = (side == "server" and direction == ">") or (side == "client" and direction == "<")
        candidate_range = (
            range(index - 1, -1, -1) if search_backward else range(index + 1, len(metadata))
        )
        for candidate_index in candidate_range:
            candidate = metadata[candidate_index]
            if candidate.get("side") != target_side:
                continue
            candidate_time = candidate.get("timestamp")
            if candidate_time is None:
                continue
            if not search_backward and candidate_time > latest_time:
                break
            if candidate.get("ioa") == ioa and candidate.get("cot") == cot:
                matches[index] = candidate_index
                break
    return matches


def _parse_ioa_part(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 0 or parsed > 255:
        return None
    return parsed


def _extract_ioa(row: Dict[str, Any]) -> Optional[int]:
    parts = [
        _parse_ioa_part(row.get("IOA 1")),
        _parse_ioa_part(row.get("IOA 2")),
        _parse_ioa_part(row.get("IOA 3")),
    ]
    if any(part is None for part in parts):
        return None
    return parts[0] + (parts[1] << 8) + (parts[2] << 16)


def _build_excel_rows_from_datapoint_list(
    datapoint_rows: List[Dict[str, Any]]
) -> List[Dict[int, Any]]:
    rows: List[Dict[int, Any]] = []
    for entry in datapoint_rows:
        if not isinstance(entry, dict):
            continue
        ioa = _extract_ioa(entry)
        rows.append(
            {
                1: entry.get("Datenpunkt / Meldetext") or "",
                2: str(ioa) if ioa is not None else "",
                3: entry.get("IEC104- Typ") or "",
                4: entry.get("Übertragungsursache") or "",
            }
        )
    return rows


def _column_letter(index: int) -> str:
    if index <= 0:
        return ""
    letters: List[str] = []
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _inline_string_cell(column_index: int, row_index: int, value: str, style_index: int = 0) -> str:
    if value is None:
        value = ""
    text = escape(str(value))
    cell_ref = f"{_column_letter(column_index)}{row_index}"
    style_attr = f' s="{style_index}"' if style_index else ""
    return f'<c r="{cell_ref}"{style_attr} t="inlineStr"><is><t>{text}</t></is></c>'


def _cell_with_style(column_index: int, row_index: int, style_index: int = 0) -> str:
    cell_ref = f"{_column_letter(column_index)}{row_index}"
    style_attr = f' s="{style_index}"' if style_index else ""
    return f'<c r="{cell_ref}"{style_attr}/>'


def _border_style_index(column_index: int, row_index: int) -> int:
    needs_right = (column_index in (5, 24, 29) and row_index >= 1) or (
        column_index in (14, 15, 26) and row_index >= 2
    )
    needs_bottom = row_index in (2, 3) or (row_index == 1 and 6 <= column_index <= 29)
    if needs_right and needs_bottom:
        return 3
    if needs_right:
        return 1
    if needs_bottom:
        return 2
    return 0


def _combine_style_index(base_style: int, border_style: int) -> int:
    if base_style == 4:
        return {0: 4, 1: 5, 2: 6, 3: 7}.get(border_style, 4)
    if base_style == 8:
        return {0: 8, 1: 9, 2: 10, 3: 11}.get(border_style, 8)
    return border_style


def _header_style_index(column_index: int, row_index: int) -> int:
    if (row_index == 1 and column_index in (1, 6, 25, 26, 27, 28, 29)) or (
        row_index == 2 and column_index in (6, 16, 25, 26, 27, 28, 29)
    ):
        base_style = 4
    elif row_index in (1, 2) and 1 <= column_index <= 5:
        base_style = 8
    else:
        base_style = 0
    border_style = _border_style_index(column_index, row_index)
    return _combine_style_index(base_style, border_style)


def _body_style_index(column_index: int, row_index: int) -> int:
    if column_index == 15 and row_index >= 3:
        base_style = 8
    else:
        base_style = 0
    border_style = _border_style_index(column_index, row_index)
    return _combine_style_index(base_style, border_style)


def _red_fill_style_index(column_index: int, row_index: int) -> int:
    border_style = _border_style_index(column_index, row_index)
    return {0: 12, 1: 13, 2: 14, 3: 15}.get(border_style, 12)


def _create_excel_styles() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<fonts count=\"2\">"
        "<font><sz val=\"11\"/><color theme=\"1\"/><name val=\"Calibri\"/><family val=\"2\"/>"
        "<scheme val=\"minor\"/></font>"
        "<font><b/><sz val=\"11\"/><color theme=\"1\"/><name val=\"Calibri\"/><family val=\"2\"/>"
        "<scheme val=\"minor\"/></font>"
        "</fonts>"
        "<fills count=\"3\">"
        "<fill><patternFill patternType=\"none\"/></fill>"
        "<fill><patternFill patternType=\"gray125\"/></fill>"
        "<fill><patternFill patternType=\"solid\"><fgColor rgb=\"FFFF0000\"/><bgColor indexed=\"64\"/></patternFill></fill>"
        "</fills>"
        "<borders count=\"4\">"
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        "<border><left/><right style=\"medium\"/><top/><bottom/><diagonal/></border>"
        "<border><left/><right/><top/><bottom style=\"medium\"/><diagonal/></border>"
        "<border><left/><right style=\"medium\"/><top/><bottom style=\"medium\"/><diagonal/></border>"
        "</borders>"
        "<cellStyleXfs count=\"1\">"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/>"
        "</cellStyleXfs>"
        "<cellXfs count=\"16\">"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyBorder=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"2\" xfId=\"0\" applyBorder=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"3\" xfId=\"0\" applyBorder=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\""
        " applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyBorder=\"1\""
        " applyFont=\"1\" applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"2\" xfId=\"0\" applyBorder=\"1\""
        " applyFont=\"1\" applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"3\" xfId=\"0\" applyBorder=\"1\""
        " applyFont=\"1\" applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyAlignment=\"1\">"
        "<alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyBorder=\"1\""
        " applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"2\" xfId=\"0\" applyBorder=\"1\""
        " applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"3\" xfId=\"0\" applyBorder=\"1\""
        " applyAlignment=\"1\"><alignment horizontal=\"center\" vertical=\"center\"/></xf>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"2\" borderId=\"0\" xfId=\"0\" applyFill=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"2\" borderId=\"1\" xfId=\"0\" applyFill=\"1\" applyBorder=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"2\" borderId=\"2\" xfId=\"0\" applyFill=\"1\" applyBorder=\"1\"/>"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"2\" borderId=\"3\" xfId=\"0\" applyFill=\"1\" applyBorder=\"1\"/>"
        "</cellXfs>"
        "<cellStyles count=\"1\">"
        "<cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/>"
        "</cellStyles>"
        "</styleSheet>"
    )


def _create_excel_workbook(headers: List[str], rows: List[Dict[int, Any]]) -> bytes:
    header_row_index = 3
    first_data_row_index = header_row_index + 1
    last_row_index = max(header_row_index, first_data_row_index + len(rows) - 1)
    last_column_index = len(headers)
    dimension = f"A1:{_column_letter(last_column_index)}{last_row_index}"

    row1_cells = {
        1: "Datenpunktliste",
        6: "Kommunikationsverlauf",
        25: "Analyse des Kommunikationsverlaufes",
    }
    row2_cells = {
        6: "Client",
        16: "Server",
        25: "Signal finden",
        27: "Auswertung",
    }

    row1_cell_entries: List[str] = []
    for col_index in range(1, last_column_index + 1):
        value = row1_cells.get(col_index)
        style_index = _header_style_index(col_index, 1)
        if value:
            row1_cell_entries.append(_inline_string_cell(col_index, 1, value, style_index))
        elif style_index:
            row1_cell_entries.append(_cell_with_style(col_index, 1, style_index))

    row2_cell_entries: List[str] = []
    for col_index in range(1, last_column_index + 1):
        value = row2_cells.get(col_index)
        style_index = _header_style_index(col_index, 2)
        if value:
            row2_cell_entries.append(_inline_string_cell(col_index, 2, value, style_index))
        else:
            row2_cell_entries.append(_cell_with_style(col_index, 2, style_index))

    header_cells = [
        _inline_string_cell(index + 1, header_row_index, header, _body_style_index(index + 1, header_row_index))
        for index, header in enumerate(headers)
    ]
    for col_index in range(1, last_column_index + 1):
        if col_index > len(headers):
            header_cells.append(
                _cell_with_style(col_index, header_row_index, _border_style_index(col_index, header_row_index))
            )

    data_rows: List[str] = []
    for offset, row in enumerate(rows):
        row_index = first_data_row_index + offset
        cell_columns = set(row.keys()) | {5, 14, 15, 24, 26, 29}
        cells = []
        for col_index in sorted(cell_columns):
            value = row.get(col_index)
            cell_value = value
            style_override = None
            if isinstance(value, dict) and "value" in value and "style" in value:
                cell_value = value.get("value")
                style_override = value.get("style")
            if style_override == "red":
                style_index = _red_fill_style_index(col_index, row_index)
            else:
                style_index = _body_style_index(col_index, row_index)
            if cell_value not in (None, ""):
                cells.append(_inline_string_cell(col_index, row_index, cell_value, style_index))
            elif style_index:
                cells.append(_cell_with_style(col_index, row_index, style_index))
        if cells:
            data_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        else:
            data_rows.append(f'<row r="{row_index}"/>')

    sheet_rows = "".join(
        [
            f'<row r="1">{"".join(row1_cell_entries)}</row>',
            f'<row r="2">{"".join(row2_cell_entries)}</row>',
            f'<row r="{header_row_index}">{"".join(header_cells)}</row>',
        ]
        + data_rows
    )
    merge_cells = (
        "<mergeCells count=\"7\">"
        "<mergeCell ref=\"A1:E1\"/>"
        "<mergeCell ref=\"F1:X1\"/>"
        "<mergeCell ref=\"Y1:AC1\"/>"
        "<mergeCell ref=\"F2:N2\"/>"
        "<mergeCell ref=\"P2:X2\"/>"
        "<mergeCell ref=\"Y2:Z2\"/>"
        "<mergeCell ref=\"AA2:AC2\"/>"
        "</mergeCells>"
    )
    sheet_content = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        f"xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<dimension ref=\"{dimension}\"/>"
        f"<sheetData>{sheet_rows}</sheetData>"
        f"{merge_cells}"
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
        "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>"
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
        "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>"
        "</Types>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_content)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", _create_excel_styles())
        zf.writestr("xl/worksheets/sheet1.xml", sheet_content)
    return buffer.getvalue()


def build_protocol_excel(
    telegram_entries: Optional[List[Dict[str, Any]]] = None,
    datapoint_rows: Optional[List[Dict[str, Any]]] = None,
    incoming_telegram_timeout: float = 0.0,
) -> bytes:
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
        "Andere Seite",
        "Datenpunktliste",
        "Auswertung",
        "Erläuterung",
        "Abweichungen",
    ]
    communication_rows, communication_metadata = _build_excel_rows_from_communication(telegram_entries or [])
    datapoint_rows = _build_excel_rows_from_datapoint_list(datapoint_rows or [])
    row_count = max(len(communication_rows), len(datapoint_rows))
    rows: List[Dict[int, Any]] = []
    for index in range(row_count):
        combined: Dict[int, Any] = {}
        if index < len(datapoint_rows):
            combined.update(datapoint_rows[index])
        if index < len(communication_rows):
            combined.update(communication_rows[index])
        rows.append(combined)
    if incoming_telegram_timeout > 0:
        matches = _find_matching_row_indices(communication_metadata, incoming_telegram_timeout)
        first_data_row_index = 4
        for source_index, target_index in matches.items():
            if source_index < len(rows):
                rows[source_index][25] = str(first_data_row_index + target_index)
        for source_index in range(len(communication_rows)):
            if 25 not in rows[source_index]:
                rows[source_index][25] = _styled_cell("", "red")
    ioa_to_row_index: Dict[str, int] = {}
    first_data_row_index = 4
    for index, row in enumerate(rows):
        ioa_value = _normalize_match_value(row.get(2))
        if ioa_value and ioa_value not in ioa_to_row_index:
            ioa_to_row_index[ioa_value] = first_data_row_index + index
    for index, row in enumerate(rows):
        ioa_value = _normalize_match_value(row.get(8)) or _normalize_match_value(row.get(18))
        if ioa_value is None:
            continue
        target_row = ioa_to_row_index.get(ioa_value)
        if target_row is not None:
            row[26] = str(target_row)
        else:
            row[26] = _styled_cell("", "red")
    return _create_excel_workbook(headers, rows)

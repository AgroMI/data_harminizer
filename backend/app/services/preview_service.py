from __future__ import annotations

from datetime import date, datetime, timezone
import re

from etl.block_detector import detect_blocks_with_positions
from etl.excel_reader import read_tabular_source
from etl.preview_schema import build_preview
from etl.type_inference import parse_date_value
from etl.types import BlockRecord, ParsedUploadSource, PreviewPayload, SheetManifestItem

PARSER_VERSION = "tabular_preview_parser_v1"
HEADER_CONTEXT_SCAN_ROWS = 5
MIN_PARALLEL_VERTICAL_MERGE_BLOCKS = 3
MERGED_ROW_ALIGNMENT_TOLERANCE = 2
LEFT_LABEL_MAX_FILL_RATIO = 0.25
LEFT_LABEL_MIN_TEXT_RATIO = 0.8
CONTEXT_DATE_SCAN_ROWS = 6
_DOTTED_DATE_RE = re.compile(r"\b((?:19|20)\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\.?\b")


def _non_empty_cell_count(rows: list[list[object]]) -> int:
    count = 0
    for row in rows:
        for value in row:
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            count += 1
    return count


def _sheet_manifest_item(
    *,
    sheet_index: int,
    sheet_name: str,
    rows: list[list[object]],
    detected_block_count: int,
) -> SheetManifestItem:
    return {
        "sheet_index": sheet_index,
        "sheet_name": sheet_name,
        "row_count": len(rows),
        "max_column_count": max((len(row) for row in rows), default=0),
        "non_empty_cell_count": _non_empty_cell_count(rows),
        "detected_block_count": detected_block_count,
    }


def _parse_warning_summary(sheet_manifest: list[SheetManifestItem]) -> list[str]:
    warnings: list[str] = []
    for item in sheet_manifest:
        if item["row_count"] == 0:
            warnings.append(f"empty_sheet:{item['sheet_name']}")
        elif item["detected_block_count"] == 0:
            warnings.append(f"no_blocks_detected:{item['sheet_name']}")
    return warnings


def _is_non_empty_cell(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _row_segment_has_header_signal(row: list[object], col_start: int, col_end: int) -> bool:
    segment = row[col_start - 1 : col_end]
    non_empty = [value for value in segment if _is_non_empty_cell(value)]
    if len(non_empty) < 2:
        return False

    strings = [str(value).strip() for value in non_empty if isinstance(value, str) and str(value).strip()]
    if len(strings) < 2:
        return False

    if (len(strings) / len(non_empty)) < 0.6:
        return False

    normalized = {value.lower() for value in strings}
    has_repeated_group_label = len(normalized) < len(strings)
    has_compact_header_tokens = len(strings) >= 3 and (sum(len(value) for value in strings) / len(strings)) <= 24
    return has_repeated_group_label or has_compact_header_tokens


def _row_segment_has_repeated_header_group(row: list[object], col_start: int, col_end: int) -> bool:
    segment = row[col_start - 1 : col_end]
    strings = [str(value).strip().lower() for value in segment if isinstance(value, str) and str(value).strip()]
    return len(strings) >= 2 and len(set(strings)) < len(strings)


def _expand_block_with_header_context(
    rows: list[list[object]],
    block: dict[str, object],
) -> dict[str, object]:
    row_start = int(block["row_start"])
    row_end = int(block["row_end"])
    col_start = int(block["col_start"])
    col_end = int(block["col_end"])

    first_row_index = row_start - 1
    if first_row_index < len(rows) and _row_segment_has_repeated_header_group(rows[first_row_index], col_start, col_end):
        return block

    scan_start = max(0, first_row_index - HEADER_CONTEXT_SCAN_ROWS)
    context_start_index: int | None = None

    for row_index in range(first_row_index - 1, scan_start - 1, -1):
        row = rows[row_index]
        if _row_segment_has_header_signal(row, col_start, col_end):
            context_start_index = row_index
            break

    if context_start_index is None:
        return block

    expanded_rows = [
        list(row[col_start - 1 : col_end])
        for row in rows[context_start_index:row_end]
    ]
    return {
        **block,
        "row_start": context_start_index + 1,
        "row_count": row_end - context_start_index,
        "rows": expanded_rows,
    }


def _expand_block_with_left_label_context(
    rows: list[list[object]],
    block: dict[str, object],
) -> dict[str, object]:
    row_start = int(block["row_start"])
    row_end = int(block["row_end"])
    col_start = int(block["col_start"])
    col_end = int(block["col_end"])
    if col_start <= 1:
        return block

    label_col_index = col_start - 2
    values: list[object] = []
    for row in rows[row_start - 1 : row_end]:
        if label_col_index >= len(row):
            continue
        value = row[label_col_index]
        if _is_non_empty_cell(value):
            values.append(value)

    if len(values) < 2:
        return block

    total_rows = max(row_end - row_start + 1, 1)
    fill_ratio = len(values) / total_rows
    text_ratio = sum(1 for value in values if isinstance(value, str) and value.strip()) / len(values)
    if fill_ratio > LEFT_LABEL_MAX_FILL_RATIO or text_ratio < LEFT_LABEL_MIN_TEXT_RATIO:
        return block

    expanded_col_start = col_start - 1
    expanded_rows = [
        list(row[expanded_col_start - 1 : col_end])
        for row in rows[row_start - 1 : row_end]
    ]
    return {
        **block,
        "col_start": expanded_col_start,
        "col_count": col_end - expanded_col_start + 1,
        "rows": expanded_rows,
    }


def _parse_context_date(value: object) -> date | None:
    parsed = parse_date_value(value)
    if parsed is not None:
        return parsed

    if not isinstance(value, str):
        return None

    match = _DOTTED_DATE_RE.search(value.strip())
    if match is None:
        return None

    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _detect_block_context_date(
    rows: list[list[object]],
    block: dict[str, object],
) -> date | None:
    row_start = int(block["row_start"])
    scan_start = max(0, row_start - CONTEXT_DATE_SCAN_ROWS - 1)
    scan_end = max(0, row_start - 1)

    for row in rows[scan_start:scan_end]:
        for value in row:
            parsed = _parse_context_date(value)
            if parsed is not None:
                return parsed

    return None


def _has_parallel_merged_row_spans(blocks: list[dict[str, object]]) -> bool:
    tall_blocks = [
        block
        for block in blocks
        if int(block["row_end"]) - int(block["row_start"]) + 1 >= 30
    ]
    for anchor in tall_blocks:
        aligned_count = 0
        for block in tall_blocks:
            if (
                abs(int(block["row_start"]) - int(anchor["row_start"])) <= MERGED_ROW_ALIGNMENT_TOLERANCE
                and abs(int(block["row_end"]) - int(anchor["row_end"])) <= MERGED_ROW_ALIGNMENT_TOLERANCE
            ):
                aligned_count += 1
        if aligned_count >= MIN_PARALLEL_VERTICAL_MERGE_BLOCKS:
            return True
    return False


def _detect_blocks_for_upload(rows: list[list[object]]) -> list[dict[str, object]]:
    detected_blocks = detect_blocks_with_positions(rows)
    merged_blocks = detect_blocks_with_positions(rows, merge_vertical_blocks=True)

    if len(merged_blocks) < len(detected_blocks) and _has_parallel_merged_row_spans(merged_blocks):
        return merged_blocks

    return detected_blocks


def parse_upload_source(file_bytes: bytes, filename: str) -> ParsedUploadSource:
    try:
        workbook = read_tabular_source(file_bytes, filename=filename)
    except Exception as exc:  # pragma: no cover - minimal scaffold safeguard
        raise ValueError("Could not parse table file. Ensure it is a valid Excel, CSV or TSV file.") from exc

    block_records: list[BlockRecord] = []
    sheet_manifest: list[SheetManifestItem] = []

    for sheet in workbook:
        sheet_index = sheet["sheet_index"]
        sheet_name = sheet["sheet_name"]
        rows = sheet["rows"]
        detected_blocks = _detect_blocks_for_upload(rows)

        sheet_manifest.append(
            _sheet_manifest_item(
                sheet_index=sheet_index,
                sheet_name=sheet_name,
                rows=rows,
                detected_block_count=len(detected_blocks),
            )
        )

        for block_number, raw_block in enumerate(detected_blocks, start=1):
            block = _expand_block_with_left_label_context(rows, raw_block)
            block = _expand_block_with_header_context(rows, block)
            context_date = _detect_block_context_date(rows, block)
            block_records.append(
                {
                    "block_id": f"S{sheet_index}_B{block_number}",
                    "sheet_name": sheet_name,
                    "row_start": block["row_start"],
                    "row_end": block["row_end"],
                    "col_start": block["col_start"],
                    "col_end": block["col_end"],
                    "row_count": block["row_count"],
                    "col_count": block["col_count"],
                    "rows": block["rows"],
                    "inferred_observation_date": context_date.isoformat() if context_date is not None else None,
                }
            )

    return {
        "preview": build_preview(file_name=filename, block_records=block_records),
        "parser_version": PARSER_VERSION,
        "sheet_manifest": sheet_manifest,
        "preview_generated_at": datetime.now(timezone.utc),
        "parse_warning_summary": _parse_warning_summary(sheet_manifest),
    }


def parse_preview(file_bytes: bytes, filename: str) -> PreviewPayload:
    return parse_upload_source(file_bytes=file_bytes, filename=filename)["preview"]

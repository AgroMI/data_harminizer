from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from etl.missing_summary import compute_missing_by_column
from etl.semantic_mapping import (
    default_canonical_dimension,
    default_canonical_measure,
    infer_default_semantic_role,
)
from etl.unit_harmonization import infer_default_unit
from etl.table_utils import is_missing, make_unique_headers, normalize_header, rows_to_dicts
from etl.type_inference import detect_date_issues, infer_column_types, is_numeric_value, parse_date_value
from etl.types import (
    BlockRecord,
    ColumnWarningCode,
    DataRow,
    ExtractedTable,
    PreviewBlock,
    PreviewPayload,
    TypeSuggestionItem,
)

PREVIEW_ROW_LIMIT = 25
TYPE_INFERENCE_ROW_LIMIT = 200
SPARSE_TEXT_COL_MAX_FILL_RATIO = 0.2
SPARSE_TEXT_COL_MIN_TEXT_RATIO = 0.8
GENERIC_COLUMN_PREFIX = "column_"
MAX_LABEL_TOKEN_LENGTH = 12
AMBIGUOUS_TYPE_RATIO = 0.35
HIGH_MISSING_RATIO = 0.5
HEADER_SCAN_LIMIT = 5
MAX_HEADER_ROWS = 2
PREAMBLE_ROW_MAX_FILL_RATIO = 0.25
SECONDARY_HEADER_STRING_RATIO = 0.85
SECONDARY_HEADER_NUMERIC_RATIO = 0.15
DENSE_TEXT_DIMENSION_MAX_MISSING_RATIO = 0.35
DENSE_TEXT_DIMENSION_MIN_SHORT_TOKEN_RATIO = 0.7
DENSE_TEXT_DIMENSION_MAX_TOKEN_LENGTH = 16


def _is_textual_non_numeric(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    cleaned = value.strip()
    if not cleaned:
        return False

    return not is_numeric_value(cleaned)


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (time, datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _column_letter(index: int) -> str:
    value = index
    letters = ""
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters or "A"


def _range_label(row_start: int, row_end: int, col_start: int, col_end: int) -> str:
    return f"{_column_letter(col_start)}{row_start}:{_column_letter(col_end)}{row_end}"


def _row_is_header_candidate(row: list[Any]) -> bool:
    non_empty_values = [value for value in row if not is_missing(value)]
    if len(non_empty_values) < 2:
        return False

    total = len(non_empty_values)
    string_ratio = sum(1 for value in non_empty_values if isinstance(value, str)) / total
    numeric_ratio = sum(1 for value in non_empty_values if is_numeric_value(value)) / total

    return string_ratio >= 0.6 and numeric_ratio <= 0.4


def _row_fill_ratio(row: list[Any]) -> float:
    if not row:
        return 0.0
    non_empty_count = sum(1 for value in row if not is_missing(value))
    return non_empty_count / len(row)


def _row_is_preamble_candidate(row: list[Any]) -> bool:
    non_empty_count = sum(1 for value in row if not is_missing(value))
    if non_empty_count <= 1:
        return True
    return _row_fill_ratio(row) <= PREAMBLE_ROW_MAX_FILL_RATIO


def _row_is_secondary_header_candidate(row: list[Any]) -> bool:
    non_empty_values = [value for value in row if not is_missing(value)]
    if len(non_empty_values) < 2:
        return False

    total = len(non_empty_values)
    string_ratio = sum(1 for value in non_empty_values if isinstance(value, str)) / total
    numeric_ratio = sum(1 for value in non_empty_values if is_numeric_value(value)) / total
    return (
        string_ratio >= SECONDARY_HEADER_STRING_RATIO
        and numeric_ratio <= SECONDARY_HEADER_NUMERIC_RATIO
    )


def _find_header_start_index(rows: list[list[Any]]) -> int | None:
    scan_limit = min(len(rows), HEADER_SCAN_LIMIT)
    if scan_limit == 0:
        return None

    if _row_is_header_candidate(rows[0]):
        return 0

    for row_index in range(1, scan_limit):
        if not _row_is_header_candidate(rows[row_index]):
            continue
        if all(_row_is_preamble_candidate(row) for row in rows[:row_index]):
            return row_index

    return None


def _leading_preamble_row_count(rows: list[list[Any]]) -> int:
    count = 0
    for row in rows[:HEADER_SCAN_LIMIT]:
        if not _row_is_preamble_candidate(row):
            break
        count += 1
    return count


def _compose_headers(
    rows: list[list[Any]],
    *,
    row_start: int,
    row_count: int,
    col_count: int,
) -> list[str]:
    headers: list[str] = []

    for col_index in range(col_count):
        parts: list[str] = []
        for row_offset in range(row_count):
            value = rows[row_start + row_offset][col_index]
            if is_missing(value):
                continue
            cleaned = str(value).strip()
            if cleaned:
                parts.append(cleaned)

        headers.append(normalize_header(" ".join(parts) if parts else None, col_index))

    return make_unique_headers(headers)


def _is_dimension_like_token(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    cleaned = value.strip()
    if not cleaned:
        return False

    return (
        not is_numeric_value(cleaned)
        and " " not in cleaned
        and len(cleaned) <= DENSE_TEXT_DIMENSION_MAX_TOKEN_LENGTH
    )


def _is_dense_generic_dimension_candidate(
    *,
    header: str,
    suggested: str,
    values: list[Any],
    missing_ratio: float,
) -> bool:
    if suggested != "text" or not header.startswith(GENERIC_COLUMN_PREFIX):
        return False
    if missing_ratio > DENSE_TEXT_DIMENSION_MAX_MISSING_RATIO:
        return False
    if len(values) < 3:
        return False

    short_token_ratio = sum(1 for value in values if _is_dimension_like_token(value)) / len(values)
    return short_token_ratio >= DENSE_TEXT_DIMENSION_MIN_SHORT_TOKEN_RATIO


def _drop_sparse_annotation_labels(headers: list[str], data_rows: list[DataRow]) -> None:
    total_rows = len(data_rows)
    if total_rows == 0:
        return

    for header in headers:
        if not header.startswith(GENERIC_COLUMN_PREFIX):
            continue

        non_empty_values = [
            row.get(header)
            for row in data_rows
            if not is_missing(row.get(header))
        ]
        if not non_empty_values:
            continue

        fill_ratio = len(non_empty_values) / total_rows
        text_ratio = (
            sum(1 for value in non_empty_values if _is_textual_non_numeric(value))
            / len(non_empty_values)
        )

        if fill_ratio > SPARSE_TEXT_COL_MAX_FILL_RATIO:
            continue
        if text_ratio < SPARSE_TEXT_COL_MIN_TEXT_RATIO:
            continue

        for row in data_rows:
            value = row.get(header)
            if not isinstance(value, str):
                continue

            cleaned = value.strip()
            if not cleaned:
                continue

            # Keep short code-like tokens (for example N40), drop descriptive labels.
            if " " in cleaned or len(cleaned) > MAX_LABEL_TOKEN_LENGTH:
                row[header] = None


def extract_table_from_block_cells(block_cells: list[list[Any]]) -> ExtractedTable:
    if not block_cells:
        return {
            "headers": [],
            "data_rows": [],
            "header_in_first_row": False,
            "header_row_count": 0,
            "data_row_start_index": 0,
        }

    col_count = max((len(row) for row in block_cells), default=0)
    normalized_rows = [row + [None] * (col_count - len(row)) for row in block_cells]
    header_start_index = _find_header_start_index(normalized_rows)
    header_in_first_row = header_start_index == 0
    header_row_count = 0

    if header_start_index is not None:
        header_row_count = 1
        while (
            header_row_count < MAX_HEADER_ROWS
            and header_start_index + header_row_count < len(normalized_rows)
            and _row_is_secondary_header_candidate(normalized_rows[header_start_index + header_row_count])
        ):
            header_row_count += 1

        unique_headers = _compose_headers(
            normalized_rows,
            row_start=header_start_index,
            row_count=header_row_count,
            col_count=col_count,
        )
        data_row_start_index = header_start_index + header_row_count
    else:
        data_row_start_index = _leading_preamble_row_count(normalized_rows)
        unique_headers = [f"{GENERIC_COLUMN_PREFIX}{idx + 1}" for idx in range(col_count)]

    data_matrix = normalized_rows[data_row_start_index:]
    data_rows = rows_to_dicts(unique_headers, data_matrix)
    _drop_sparse_annotation_labels(unique_headers, data_rows)

    return {
        "headers": unique_headers,
        "data_rows": data_rows,
        "header_in_first_row": header_in_first_row,
        "header_row_count": header_row_count,
        "data_row_start_index": data_row_start_index,
    }


def extract_full_rows_from_preview_block(block: dict[str, Any]) -> tuple[list[str], list[DataRow]]:
    block_cells = block.get("_cells", [])
    if not isinstance(block_cells, list):
        return [], []

    normalized_cells = [list(row) for row in block_cells if isinstance(row, list)]
    table = extract_table_from_block_cells(normalized_cells)
    return table["headers"], table["data_rows"]


def extract_table_details_from_preview_block(block: dict[str, Any]) -> ExtractedTable:
    block_cells = block.get("_cells", [])
    if not isinstance(block_cells, list):
        return {
            "headers": [],
            "data_rows": [],
            "header_in_first_row": False,
            "header_row_count": 0,
            "data_row_start_index": 0,
        }

    normalized_cells = [list(row) for row in block_cells if isinstance(row, list)]
    return extract_table_from_block_cells(normalized_cells)


def _column_warning_codes(
    *,
    header: str,
    suggested: str,
    values: list[Any],
    missing_ratio: float,
    has_date_issue: bool,
) -> list[ColumnWarningCode]:
    warnings: list[ColumnWarningCode] = []
    is_dimension_like = _is_dense_generic_dimension_candidate(
        header=header,
        suggested=suggested,
        values=values,
        missing_ratio=missing_ratio,
    )

    if missing_ratio >= HIGH_MISSING_RATIO:
        warnings.append("high_missing")

    if header.startswith(GENERIC_COLUMN_PREFIX) and suggested == "text" and not is_dimension_like:
        warnings.append("annotation_like")

    if has_date_issue:
        warnings.append("date_parse_issue")

    if values:
        numeric_ratio = sum(1 for value in values if is_numeric_value(value)) / len(values)
        date_ratio = sum(1 for value in values if parse_date_value(value) is not None) / len(values)

        if suggested == "text" and max(numeric_ratio, date_ratio) >= AMBIGUOUS_TYPE_RATIO:
            warnings.append("ambiguous_type")

    return warnings


def _enrich_type_suggestions(
    *,
    type_suggestions: list[TypeSuggestionItem],
    data_rows: list[DataRow],
    missing_by_column: list[dict[str, Any]],
    date_issues: list[dict[str, Any]],
) -> list[TypeSuggestionItem]:
    missing_ratio_by_column = {
        item["column"]: float(item.get("ratio", 0.0))
        for item in missing_by_column
        if isinstance(item, dict)
    }
    date_issue_columns = {
        item["column"]
        for item in date_issues
        if isinstance(item, dict) and isinstance(item.get("column"), str)
    }

    enriched: list[TypeSuggestionItem] = []
    for item in type_suggestions:
        column = item["column"]
        suggested = item["suggested"]
        values = [
            row.get(column)
            for row in data_rows
            if not is_missing(row.get(column))
        ]
        warnings = _column_warning_codes(
            header=column,
            suggested=suggested,
            values=values,
            missing_ratio=missing_ratio_by_column.get(column, 0.0),
            has_date_issue=column in date_issue_columns,
        )
        if _is_dense_generic_dimension_candidate(
            header=column,
            suggested=suggested,
            values=values,
            missing_ratio=missing_ratio_by_column.get(column, 0.0),
        ):
            semantic_role = "dimension"
        else:
            semantic_role = infer_default_semantic_role(
                column=column,
                suggested_type=suggested,
                warnings=warnings,
            )
        canonical_measure = default_canonical_measure(semantic_role, column)

        enriched.append(
            {
                "column": column,
                "suggested": suggested,
                "type_override": item.get("type_override"),
                "semantic_role": semantic_role,
                "canonical_measure": canonical_measure,
                "canonical_dimension": default_canonical_dimension(semantic_role, column),
                "unit": infer_default_unit(column, canonical_measure),
                "warnings": warnings,
            }
        )

    return enriched


def build_preview(*, file_name: str, block_records: list[BlockRecord]) -> PreviewPayload:
    blocks: list[PreviewBlock] = []

    for block in block_records:
        block_cells = block["rows"]
        if not block_cells:
            continue

        table = extract_table_from_block_cells(block_cells)
        headers = table["headers"]
        data_rows = table["data_rows"]

        sample_rows = [
            {header: _serialize_cell(row.get(header)) for header in headers}
            for row in data_rows[:PREVIEW_ROW_LIMIT]
        ]

        type_suggestions = infer_column_types(
            headers,
            data_rows,
            row_limit=TYPE_INFERENCE_ROW_LIMIT,
        )
        date_issues = detect_date_issues(
            headers,
            data_rows,
            type_suggestions,
            row_limit=TYPE_INFERENCE_ROW_LIMIT,
        )
        missing_by_column = compute_missing_by_column(headers, data_rows)
        type_suggestions = _enrich_type_suggestions(
            type_suggestions=type_suggestions,
            data_rows=data_rows,
            missing_by_column=missing_by_column,
            date_issues=date_issues,
        )

        row_start = int(block["row_start"])
        row_end = int(block["row_end"])
        col_start = int(block["col_start"])
        col_end = int(block["col_end"])

        blocks.append(
            {
                "block_id": block["block_id"],
                "sheet": block["sheet_name"],
                "range": _range_label(row_start, row_end, col_start, col_end),
                "row_start": row_start,
                "row_end": row_end,
                "col_start": col_start,
                "col_end": col_end,
                "row_count": int(block["row_count"]),
                "col_count": int(block["col_count"]),
                "headers": headers,
                "sample_rows": sample_rows,
                "missing_by_column": missing_by_column,
                "type_suggestions": type_suggestions,
                "date_issues": date_issues,
                "_cells": [[_serialize_cell(value) for value in row] for row in block_cells],
            }
        )

    return {
        "file_name": file_name,
        "block_count": len(blocks),
        "blocks": blocks,
    }

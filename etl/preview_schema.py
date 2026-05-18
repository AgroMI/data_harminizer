from __future__ import annotations

from datetime import date, datetime, time
import re
from typing import Any

from etl.missing_summary import compute_missing_by_column
from etl.semantic_mapping import (
    default_canonical_dimension,
    default_canonical_measure,
    infer_default_canonical_dimension,
    infer_default_semantic_role,
)
from etl.unit_harmonization import infer_default_unit, is_supported_unit_for_measure
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
MAX_HEADER_ROWS = 3
PREAMBLE_ROW_MAX_FILL_RATIO = 0.25
SECONDARY_HEADER_STRING_RATIO = 0.85
SECONDARY_HEADER_NUMERIC_RATIO = 0.15
DENSE_TEXT_DIMENSION_MAX_MISSING_RATIO = 0.35
DENSE_TEXT_DIMENSION_MIN_SHORT_TOKEN_RATIO = 0.7
DENSE_TEXT_DIMENSION_MAX_TOKEN_LENGTH = 16
REPEATED_TEXT_DIMENSION_MAX_UNIQUE_RATIO = 0.6
REPEATED_TEXT_DIMENSION_MAX_UNIQUE_VALUES = 32
_WEAK_SUMMARY_MEASURE_RE = re.compile(r"^[a-z]{1,3}$")


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


_PREAMBLE_UNIT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("kg/parc", ("kg/parc", "kg_parc", "parc.")),
    ("t/ha", ("t/ha", "t_ha")),
    ("kg/ha", ("kg/ha", "kg_ha")),
    ("%", ("%", "pct", "percent", "víz", "viz", "nedvesség", "nedvesseg")),
    ("cm", (" cm", "_cm")),
    ("m", (" m", "_m")),
]

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_DOTTED_DATE_RE = re.compile(r"\b((?:19|20)\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\.?\b")

_MEASURE_BY_UNIT: dict[str, str] = {
    "kg/ha": "yield",
    "t/ha": "yield",
    "kg/parc": "yield",
    "%": "moisture",
    "cm": "plant_height",
    "m": "plant_height",
}


def _scan_preamble_for_block_unit(rows: list[list[Any]], header_start_index: int) -> str | None:
    if header_start_index == 0:
        return None
    preamble_text = " ".join(
        str(cell).strip().lower()
        for row in rows[:header_start_index]
        for cell in row
        if isinstance(cell, str) and str(cell).strip()
    )
    for unit, tokens in _PREAMBLE_UNIT_PATTERNS:
        if any(token in preamble_text for token in tokens):
            return unit
    return None


def _infer_measure_from_block_unit(block_unit: str | None) -> str | None:
    if block_unit is None:
        return None
    return _MEASURE_BY_UNIT.get(block_unit)


def _scan_preamble_for_year(rows: list[list[Any]], header_start_index: int) -> int | None:
    if header_start_index == 0:
        return None
    preamble_text = " ".join(
        str(cell).strip()
        for row in rows[:header_start_index]
        for cell in row
        if isinstance(cell, str) and str(cell).strip()
    )
    match = _YEAR_RE.search(preamble_text)
    return int(match.group(1)) if match else None


def _scan_preamble_for_observation_date(rows: list[list[Any]], header_start_index: int) -> date | None:
    if header_start_index == 0:
        return None

    for row in rows[:header_start_index]:
        for cell in row:
            parsed = parse_date_value(cell)
            if parsed is not None:
                return parsed

            if not isinstance(cell, str):
                continue

            match = _DOTTED_DATE_RE.search(cell.strip())
            if match is None:
                continue

            year, month, day = (int(part) for part in match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                continue

    return None


def _extract_year_from_filename(file_name: str) -> int | None:
    match = _YEAR_RE.search(file_name)
    return int(match.group(1)) if match else None


def _row_is_header_candidate(row: list[Any]) -> bool:
    non_empty_values = [value for value in row if not is_missing(value)]
    if len(non_empty_values) < 2:
        return False
    if _row_is_uniform_merged(row):
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


def _row_is_uniform_merged(row: list[Any]) -> bool:
    """True when every non-empty cell carries the same string value.

    After merged-cell expansion a full-width title or metadata row looks like
    ["Koltay búza 2007.", "Koltay búza 2007.", ...].  It is structurally a
    preamble, not a header with distinct column names.
    """
    strings = [str(v).strip() for v in row if isinstance(v, str) and str(v).strip()]
    return len(strings) >= 2 and len(set(strings)) == 1


def _row_is_preamble_candidate(row: list[Any]) -> bool:
    non_empty_count = sum(1 for value in row if not is_missing(value))
    if non_empty_count <= 1:
        return True
    if _row_is_uniform_merged(row):
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


def _is_repeated_text_dimension_candidate(
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

    normalized_values = [
        str(value).strip()
        for value in values
        if isinstance(value, str) and str(value).strip()
    ]
    if len(normalized_values) < 3:
        return False

    unique_values = {value.lower() for value in normalized_values}
    unique_ratio = len(unique_values) / len(normalized_values)
    if len(unique_values) < 2:
        return False
    if len(unique_values) > REPEATED_TEXT_DIMENSION_MAX_UNIQUE_VALUES:
        return False
    return unique_ratio <= REPEATED_TEXT_DIMENSION_MAX_UNIQUE_RATIO


def _row_is_empty_dict(row: DataRow) -> bool:
    return all(is_missing(value) for value in row.values())


def _group_label_candidate_headers(headers: list[str], data_rows: list[DataRow]) -> set[str]:
    total_rows = len(data_rows)
    if total_rows == 0:
        return set()

    candidates: set[str] = set()
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

        header_index = headers.index(header)
        next_header = headers[header_index + 1] if header_index + 1 < len(headers) else None
        next_values = [
            row.get(next_header)
            for row in data_rows
            if next_header is not None and not is_missing(row.get(next_header))
        ]
        has_replicate_neighbor = (
            isinstance(next_header, str)
            and infer_default_canonical_dimension(next_header, values=next_values) == "replicate"
        )

        unique_values = {
            str(value).strip().lower()
            for value in non_empty_values
            if isinstance(value, str) and str(value).strip()
        }
        inferred_dimension = infer_default_canonical_dimension(header, values=non_empty_values)
        if len(unique_values) < 2 and not (
            has_replicate_neighbor and inferred_dimension == "variety"
        ):
            continue

        candidates.add(header)

    return candidates


def _forward_fill_group_labels(headers: list[str], data_rows: list[DataRow]) -> None:
    candidate_headers = _group_label_candidate_headers(headers, data_rows)
    if not candidate_headers:
        return

    for header in candidate_headers:
        group_rows: list[DataRow] = []
        for row in data_rows + [{}]:
            if not row or _row_is_empty_dict(row):
                if group_rows:
                    labels = [
                        candidate
                        for candidate in (group_row.get(header) for group_row in group_rows)
                        if not is_missing(candidate)
                    ]
                    if labels:
                        label = labels[0]
                        for group_row in group_rows:
                            if is_missing(group_row.get(header)):
                                group_row[header] = label
                group_rows = []
                continue

            group_rows.append(row)


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


def _drop_fully_empty_data_rows(data_rows: list[DataRow]) -> list[DataRow]:
    return [row for row in data_rows if not _row_is_empty_dict(row)]


def _build_extracted_table(
    *,
    headers: list[str],
    data_matrix: list[list[Any]],
    header_in_first_row: bool,
    header_row_count: int,
    data_row_start_index: int,
    inferred_unit: str | None,
    inferred_year: int | None = None,
    inferred_observation_date: date | None = None,
) -> ExtractedTable:
    data_rows = rows_to_dicts(headers, data_matrix)
    _forward_fill_group_labels(headers, data_rows)
    _drop_sparse_annotation_labels(headers, data_rows)
    data_rows = _drop_fully_empty_data_rows(data_rows)

    return {
        "headers": headers,
        "data_rows": data_rows,
        "header_in_first_row": header_in_first_row,
        "header_row_count": header_row_count,
        "data_row_start_index": data_row_start_index,
        "inferred_unit": inferred_unit,
        "inferred_year": inferred_year,
        "inferred_observation_date": inferred_observation_date,
    }


def _extract_table_with_resolved_headers(
    block_cells: list[list[Any]],
    *,
    headers: list[str],
    data_row_start_index: int,
    header_in_first_row: bool,
    header_row_count: int,
    inferred_unit: str | None,
    inferred_year: int | None = None,
    inferred_observation_date: date | None = None,
) -> ExtractedTable:
    col_count = max((len(row) for row in block_cells), default=0)
    normalized_rows = [row + [None] * (col_count - len(row)) for row in block_cells]
    data_matrix = normalized_rows[data_row_start_index:]
    return _build_extracted_table(
        headers=headers,
        data_matrix=data_matrix,
        header_in_first_row=header_in_first_row,
        header_row_count=header_row_count,
        data_row_start_index=data_row_start_index,
        inferred_unit=inferred_unit,
        inferred_year=inferred_year,
        inferred_observation_date=inferred_observation_date,
    )


def _all_headers_generic(headers: list[str]) -> bool:
    return bool(headers) and all(header.startswith(GENERIC_COLUMN_PREFIX) for header in headers)


def _is_header_anchor_table(table: ExtractedTable) -> bool:
    return table["header_row_count"] > 0 and not _all_headers_generic(table["headers"])


def _should_inherit_shared_headers(table: ExtractedTable) -> bool:
    return table["header_row_count"] == 0 and _all_headers_generic(table["headers"])


def _weak_summary_measure_name(column: Any) -> bool:
    return isinstance(column, str) and bool(_WEAK_SUMMARY_MEASURE_RE.fullmatch(column.strip().lower()))


def classify_block_semantics(block: dict[str, Any]) -> dict[str, Any]:
    suggestions = block.get("type_suggestions", [])
    if not isinstance(suggestions, list):
        return {
            "semantic_classification": "unknown",
            "classification_reasons": ["missing_type_suggestions"],
            "commit_decision": "commit_observations",
            "skip_reason": None,
        }

    measure_columns = [item for item in suggestions if isinstance(item, dict) and item.get("semantic_role") == "measure"]
    dimension_columns = [item for item in suggestions if isinstance(item, dict) and item.get("semantic_role") == "dimension"]
    canonical_measure_count = sum(
        1 for item in measure_columns if isinstance(item.get("canonical_measure"), str) and str(item.get("canonical_measure")).strip()
    )
    measure_unit_count = sum(
        1 for item in measure_columns if isinstance(item.get("unit"), str) and str(item.get("unit")).strip()
    )
    canonical_dimensions = {
        str(item.get("canonical_dimension"))
        for item in dimension_columns
        if isinstance(item.get("canonical_dimension"), str) and str(item.get("canonical_dimension")).strip()
    }
    weak_measure_count = sum(
        1 for item in measure_columns if _weak_summary_measure_name(item.get("column"))
    )

    reasons = [
        f"measure_columns={len(measure_columns)}",
        f"canonical_measures={canonical_measure_count}",
        f"measure_units={measure_unit_count}",
        f"canonical_dimensions={','.join(sorted(canonical_dimensions)) or 'none'}",
        f"weak_measure_names={weak_measure_count}",
    ]

    has_structural_dimensions = bool(canonical_dimensions)
    has_observation_measure_signal = canonical_measure_count > 0 or measure_unit_count > 0
    if measure_columns and has_structural_dimensions and has_observation_measure_signal:
        return {
            "semantic_classification": "observation_like",
            "classification_reasons": reasons,
            "commit_decision": "commit_observations",
            "skip_reason": None,
        }

    if (
        len(measure_columns) >= 3
        and not canonical_dimensions
        and canonical_measure_count == 0
        and measure_unit_count == 0
        and weak_measure_count >= max(3, len(measure_columns) - 1)
    ):
        return {
            "semantic_classification": "summary_like",
            "classification_reasons": reasons,
            "commit_decision": "skip_summary_block",
            "skip_reason": "summary_like_block",
        }

    return {
        "semantic_classification": "unknown",
        "classification_reasons": reasons,
        "commit_decision": "commit_observations",
        "skip_reason": None,
    }
def extract_table_from_block_cells(block_cells: list[list[Any]]) -> ExtractedTable:
    if not block_cells:
        return {
            "headers": [],
            "data_rows": [],
            "header_in_first_row": False,
            "header_row_count": 0,
            "data_row_start_index": 0,
            "inferred_unit": None,
            "inferred_year": None,
            "inferred_observation_date": None,
        }

    col_count = max((len(row) for row in block_cells), default=0)
    normalized_rows = [row + [None] * (col_count - len(row)) for row in block_cells]
    header_start_index = _find_header_start_index(normalized_rows)
    header_in_first_row = header_start_index == 0
    header_row_count = 0
    inferred_unit = _scan_preamble_for_block_unit(normalized_rows, header_start_index or 0)
    inferred_year = _scan_preamble_for_year(normalized_rows, header_start_index or 0)
    inferred_observation_date = _scan_preamble_for_observation_date(normalized_rows, header_start_index or 0)

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
    return _build_extracted_table(
        headers=unique_headers,
        data_matrix=data_matrix,
        header_in_first_row=header_in_first_row,
        header_row_count=header_row_count,
        data_row_start_index=data_row_start_index,
        inferred_unit=inferred_unit,
        inferred_year=inferred_year,
        inferred_observation_date=inferred_observation_date,
    )


def extract_full_rows_from_preview_block(block: dict[str, Any]) -> tuple[list[str], list[DataRow]]:
    table = extract_table_details_from_preview_block(block)
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
            "inferred_unit": None,
            "inferred_year": None,
            "inferred_observation_date": None,
        }

    normalized_cells = [list(row) for row in block_cells if isinstance(row, list)]
    resolved_headers = block.get("_resolved_headers")
    data_row_start_index = block.get("_data_row_start_index")
    block_inferred_year = block.get("inferred_year")
    block_inferred_observation_date = parse_date_value(block.get("inferred_observation_date"))
    if (
        isinstance(resolved_headers, list)
        and all(isinstance(header, str) for header in resolved_headers)
        and isinstance(data_row_start_index, int)
        and data_row_start_index >= 0
    ):
        return _extract_table_with_resolved_headers(
            normalized_cells,
            headers=list(resolved_headers),
            data_row_start_index=data_row_start_index,
            header_in_first_row=bool(block.get("_header_in_first_row")),
            header_row_count=int(block.get("_header_row_count") or 0),
            inferred_unit=block.get("_inferred_unit") if isinstance(block.get("_inferred_unit"), str) else None,
            inferred_year=int(block_inferred_year) if isinstance(block_inferred_year, int) else None,
            inferred_observation_date=block_inferred_observation_date,
        )

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
    ) or _is_repeated_text_dimension_candidate(
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
    block_unit: str | None = None,
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
        inferred_canonical_dimension = infer_default_canonical_dimension(column, values=values)
        warnings = _column_warning_codes(
            header=column,
            suggested=suggested,
            values=values,
            missing_ratio=missing_ratio_by_column.get(column, 0.0),
            has_date_issue=column in date_issue_columns,
        )
        if inferred_canonical_dimension is not None:
            warnings = [warning for warning in warnings if warning != "annotation_like"]
        if inferred_canonical_dimension is not None and suggested == "text":
            semantic_role = "dimension"
        elif _is_dense_generic_dimension_candidate(
            header=column,
            suggested=suggested,
            values=values,
            missing_ratio=missing_ratio_by_column.get(column, 0.0),
        ) or _is_repeated_text_dimension_candidate(
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
        if semantic_role == "measure" and canonical_measure is None:
            canonical_measure = _infer_measure_from_block_unit(block_unit)  # type: ignore[assignment]
        # Pass actual column values so replicate detection works even for generic column names
        canonical_dimension = (
            inferred_canonical_dimension
            if semantic_role == "dimension"
            else default_canonical_dimension(semantic_role, column)
        )

        unit = infer_default_unit(column, canonical_measure)
        if unit is None and block_unit is not None and canonical_measure is not None:
            if is_supported_unit_for_measure(canonical_measure, block_unit):
                unit = block_unit  # type: ignore[assignment]

        enriched.append(
            {
                "column": column,
                "suggested": suggested,
                "type_override": item.get("type_override"),
                "semantic_role": semantic_role,
                "canonical_measure": canonical_measure,
                "canonical_dimension": canonical_dimension,
                "unit": unit,
                "warnings": warnings,
            }
        )

    return enriched


def build_preview(
    *,
    file_name: str,
    block_records: list[BlockRecord],
    inherit_shared_headers: bool = True,
) -> PreviewPayload:
    blocks: list[PreviewBlock] = []
    shared_header_anchors: dict[tuple[str, int, int], dict[str, Any]] = {}
    filename_year = _extract_year_from_filename(file_name)

    for block in block_records:
        block_cells = block["rows"]
        if not block_cells:
            continue

        table = extract_table_from_block_cells(block_cells)
        sheet_name = str(block["sheet_name"])
        col_start = int(block["col_start"])
        col_end = int(block["col_end"])
        col_span_key = (sheet_name, col_start, col_end)
        inherited_from_block_id: str | None = None

        anchor = shared_header_anchors.get(col_span_key)
        if (
            inherit_shared_headers
            and anchor is not None
            and _should_inherit_shared_headers(table)
            and len(anchor["headers"]) == max((len(row) for row in block_cells), default=0)
        ):
            table = _extract_table_with_resolved_headers(
                block_cells,
                headers=list(anchor["headers"]),
                data_row_start_index=0,
                header_in_first_row=False,
                header_row_count=0,
                inferred_unit=anchor["inferred_unit"],
                inferred_year=anchor["inferred_year"],
                inferred_observation_date=anchor.get("inferred_observation_date"),
            )
            inherited_from_block_id = anchor["block_id"]

        headers = table["headers"]
        data_rows = table["data_rows"]

        # Preamble year takes priority; fall back to filename year
        effective_inferred_year = table.get("inferred_year") if table.get("inferred_year") is not None else filename_year
        block_record_observation_date = parse_date_value(block.get("inferred_observation_date"))
        inferred_observation_date = table.get("inferred_observation_date") or block_record_observation_date

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
            block_unit=table.get("inferred_unit"),
        )

        row_start = int(block["row_start"])
        row_end = int(block["row_end"])

        if inherit_shared_headers and inherited_from_block_id is None and _is_header_anchor_table(table):
            shared_header_anchors[col_span_key] = {
                "block_id": block["block_id"],
                "headers": list(headers),
                "inferred_unit": table.get("inferred_unit"),
                "inferred_year": table.get("inferred_year"),
                "inferred_observation_date": table.get("inferred_observation_date"),
            }

        preview_block: PreviewBlock = {
            "block_id": block["block_id"],
            "sheet": sheet_name,
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
            "inferred_year": effective_inferred_year,
            "inferred_observation_date": inferred_observation_date.isoformat() if isinstance(inferred_observation_date, date) else None,
            "_cells": [[_serialize_cell(value) for value in row] for row in block_cells],
            "_resolved_headers": list(headers),
            "_header_in_first_row": table["header_in_first_row"],
            "_header_row_count": table["header_row_count"],
            "_data_row_start_index": table["data_row_start_index"],
            "_inferred_unit": table.get("inferred_unit"),
            "_inherited_headers_from_block_id": inherited_from_block_id,
        }
        preview_block.update(classify_block_semantics(preview_block))
        blocks.append(preview_block)

    return {
        "file_name": file_name,
        "block_count": len(blocks),
        "blocks": blocks,
        "year_override": None,
    }

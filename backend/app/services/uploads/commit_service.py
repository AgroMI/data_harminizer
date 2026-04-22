from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from psycopg import Connection
from psycopg.types.json import Json

from backend.app.db import get_conn
from backend.app.services.uploads.common import (
    DEFAULT_BLOCK_ID,
    DEFAULT_SOURCE_SHEET,
    CommitResult,
    PreparedObservationRow,
    PreviewBlock,
    PreviewPayload,
    StagingInsertRow,
    UPLOAD_STATUS_COMMITTED,
    UPLOAD_STATUS_FAILED,
    dimension_text_value,
    normalize_canonical_dimension,
    normalize_canonical_measure,
    normalize_supported_unit_value,
)
from backend.app.services.uploads.preview_service import (
    ensure_preview_mapping_defaults,
    extract_blocks,
    fetch_preview,
    validate_preview_semantics,
)
from etl.preview_schema import extract_table_details_from_preview_block
from etl.quality_validation import validate_observation_records
from etl.type_inference import parse_date_value, to_numeric_value
from etl.unit_harmonization import normalize_measure_value

DELETE_HARMONIZED_SQL = "DELETE FROM harmonized.observations WHERE upload_session_id = %s"
DELETE_STAGING_SQL = "DELETE FROM staging.observations WHERE upload_session_id = %s"

INSERT_STAGING_SQL = """
INSERT INTO staging.observations (
    upload_session_id,
    block_id,
    source_sheet,
    source_row_index,
    source_column,
    observation_date,
    plot_id,
    variety,
    treatment,
    location,
    variable,
    value,
    unit,
    normalized_value,
    normalized_unit,
    validation_status,
    quality_flags,
    dimensions_json
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_HARMONIZED_SQL = """
INSERT INTO harmonized.observations (
    upload_session_id,
    block_id,
    source_sheet,
    source_row_index,
    source_column,
    observation_date,
    plot_id,
    variety,
    treatment,
    location,
    variable,
    value,
    unit,
    normalized_value,
    normalized_unit,
    validation_status,
    quality_flags,
    dimensions_json
)
SELECT
    upload_session_id,
    block_id,
    source_sheet,
    source_row_index,
    source_column,
    observation_date,
    plot_id,
    variety,
    treatment,
    location,
    variable,
    value,
    unit,
    normalized_value,
    normalized_unit,
    validation_status,
    quality_flags,
    dimensions_json
FROM staging.observations
WHERE upload_session_id = %s
  AND variable IS NOT NULL
  AND length(trim(variable)) > 0
"""

UPDATE_UPLOAD_STATUS_SQL = """
UPDATE raw.upload_sessions
SET status = %s, updated_at = now()
WHERE id = %s
"""

UPDATE_UPLOAD_FAILURE_SQL = """
UPDATE raw.upload_sessions
SET status = %s, preview_json = %s, updated_at = now()
WHERE id = %s
"""


def commit_upload_session(upload_id: str) -> CommitResult:
    preview_json: PreviewPayload = {}
    staging_rows = 0
    harmonized_rows = 0

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                preview_json, blocks = prepare_commit_blocks(cur, upload_id)
                staging_rows, harmonized_rows = rebuild_harmonized_rows(
                    conn,
                    upload_id=upload_id,
                    blocks=blocks,
                )
                cur.execute(UPDATE_UPLOAD_STATUS_SQL, (UPLOAD_STATUS_COMMITTED, upload_id))

            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as exc:  # pragma: no cover - defensive branch for DB/runtime errors
            conn.rollback()
            mark_commit_failure(conn, upload_id=upload_id, preview_json=preview_json, error_message=str(exc))
            raise HTTPException(status_code=500, detail=f"Commit failed: {exc}") from exc

    return CommitResult(
        id=upload_id,
        status=UPLOAD_STATUS_COMMITTED,
        staging_rows=staging_rows,
        harmonized_rows=harmonized_rows,
    )


def prepare_commit_blocks(cur: Any, upload_id: str) -> tuple[PreviewPayload, list[PreviewBlock]]:
    preview_json = fetch_preview(cur, upload_id, for_update=True)
    ensure_preview_mapping_defaults(preview_json)
    validate_preview_semantics(preview_json)
    return preview_json, extract_blocks(preview_json)


def rebuild_harmonized_rows(
    conn: Connection[Any],
    *,
    upload_id: str,
    blocks: list[PreviewBlock],
) -> tuple[int, int]:
    prepared_rows = build_all_staging_rows(upload_id=upload_id, blocks=blocks)
    validate_observation_records(prepared_rows)
    insert_rows = [record_to_staging_insert_row(record) for record in prepared_rows]

    with conn.cursor() as cur:
        clear_existing_rows(cur, upload_id)
        staging_rows = insert_staging_rows(cur, insert_rows)
        harmonized_rows = insert_harmonized_rows(cur, upload_id)

    return staging_rows, harmonized_rows


def clear_existing_rows(cur: Any, upload_id: str) -> None:
    cur.execute(DELETE_HARMONIZED_SQL, (upload_id,))
    cur.execute(DELETE_STAGING_SQL, (upload_id,))


def insert_staging_rows(cur: Any, insert_rows: list[StagingInsertRow]) -> int:
    if not insert_rows:
        return 0
    cur.executemany(INSERT_STAGING_SQL, insert_rows)
    return len(insert_rows)


def insert_harmonized_rows(cur: Any, upload_id: str) -> int:
    cur.execute(INSERT_HARMONIZED_SQL, (upload_id,))
    return max(cur.rowcount, 0)


def build_all_staging_rows(
    *,
    upload_id: str,
    blocks: list[PreviewBlock],
) -> list[PreparedObservationRow]:
    prepared_rows: list[PreparedObservationRow] = []
    for block in blocks:
        prepared_rows.extend(build_staging_rows(upload_id=upload_id, block=block))
    return prepared_rows


def build_staging_rows(*, upload_id: str, block: PreviewBlock) -> list[PreparedObservationRow]:
    table = extract_table_details_from_preview_block(block)
    headers = table["headers"]
    data_rows = table["data_rows"]
    if not headers or not data_rows:
        return []

    measure_columns, date_column = resolve_block_columns(block)
    if not measure_columns:
        return []

    block_context = build_block_context(block=block, table=table, date_column=date_column)
    insert_rows: list[PreparedObservationRow] = []
    for source_row_index, data_row in iter_block_data_rows(block=block, table=table):
        insert_rows.extend(
            build_data_row_observations(
                upload_id=upload_id,
                block_context=block_context,
                data_row=data_row,
                source_row_index=source_row_index,
                measure_columns=measure_columns,
            )
        )
    return insert_rows


def resolve_block_columns(block: PreviewBlock) -> tuple[list[dict[str, Any]], str | None]:
    suggestions = block.get("type_suggestions", [])
    if not isinstance(suggestions, list):
        return [], None

    measure_columns: list[dict[str, Any]] = []
    date_column: str | None = None
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        semantic_role = item.get("semantic_role")
        if not isinstance(column, str) or not isinstance(semantic_role, str):
            continue
        if semantic_role == "measure":
            measure_columns.append(item)
            continue
        if semantic_role == "date" and date_column is None:
            date_column = column

    return measure_columns, date_column


def build_block_context(
    *,
    block: PreviewBlock,
    table: dict[str, Any],
    date_column: str | None,
) -> dict[str, Any]:
    block_id = str(block.get("block_id") or DEFAULT_BLOCK_ID)
    source_sheet = str(block.get("sheet") or DEFAULT_SOURCE_SHEET)
    data_row_start_index = table.get("data_row_start_index")
    if not isinstance(data_row_start_index, int) or data_row_start_index < 0:
        data_row_start_index = 1 if table["header_in_first_row"] else 0
    return {
        "block": block,
        "block_id": block_id,
        "source_sheet": source_sheet,
        "date_column": date_column,
        "block_row_start": int(block.get("row_start") or 1),
        "data_row_start_index": data_row_start_index,
        "requires_observation_date": date_column is not None,
    }


def iter_block_data_rows(
    *,
    block: PreviewBlock,
    table: dict[str, Any],
) -> list[tuple[int, dict[str, Any]]]:
    data_rows = table["data_rows"]
    block_row_start = int(block.get("row_start") or 1)
    data_row_start_index = table.get("data_row_start_index")
    if not isinstance(data_row_start_index, int) or data_row_start_index < 0:
        data_row_start_index = 1 if table["header_in_first_row"] else 0

    return [
        (block_row_start + data_row_start_index + row_offset, data_row)
        for row_offset, data_row in enumerate(data_rows)
    ]


def build_data_row_observations(
    *,
    upload_id: str,
    block_context: dict[str, Any],
    data_row: dict[str, Any],
    source_row_index: int,
    measure_columns: list[dict[str, Any]],
) -> list[PreparedObservationRow]:
    observation_date = parse_observation_date(data_row, block_context["date_column"])
    dimension_values = canonical_dimension_payload(block_context["block"], data_row)
    dimensions_json = {key: value for key, value in dimension_values.items() if value is not None}

    rows: list[PreparedObservationRow] = []
    for measure in measure_columns:
        record = build_measure_observation(
            upload_id=upload_id,
            block_context=block_context,
            data_row=data_row,
            source_row_index=source_row_index,
            observation_date=observation_date,
            dimension_values=dimension_values,
            dimensions_json=dimensions_json,
            measure=measure,
        )
        if record is not None:
            rows.append(record)
    return rows


def parse_observation_date(data_row: dict[str, Any], date_column: str | None) -> date | None:
    if date_column is None:
        return None
    return parse_date_value(data_row.get(date_column))


def build_measure_observation(
    *,
    upload_id: str,
    block_context: dict[str, Any],
    data_row: dict[str, Any],
    source_row_index: int,
    observation_date: date | None,
    dimension_values: dict[str, str | None],
    dimensions_json: dict[str, str],
    measure: dict[str, Any],
) -> PreparedObservationRow | None:
    canonical_measure = normalize_canonical_measure(measure.get("canonical_measure"))
    if canonical_measure is None:
        return None

    column = str(measure.get("column"))
    numeric_value, unit, normalized_value, normalized_unit = normalize_measure_observation(
        data_row=data_row,
        column=column,
        canonical_measure=canonical_measure,
        measure=measure,
    )

    return {
        "upload_session_id": upload_id,
        "block_id": block_context["block_id"],
        "source_sheet": block_context["source_sheet"],
        "source_row_index": source_row_index,
        "source_column": column,
        "observation_date": observation_date,
        "plot_id": dimension_values["plot_id"],
        "variety": dimension_values["variety"],
        "treatment": dimension_values["treatment"],
        "location": dimension_values["location"],
        "variable": canonical_measure,
        "value": numeric_value,
        "unit": unit,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "dimensions_json": dimensions_json,
        "validation_status": "valid",
        "quality_flags": [],
        "_requires_observation_date": block_context["requires_observation_date"],
    }


def normalize_measure_observation(
    *,
    data_row: dict[str, Any],
    column: str,
    canonical_measure: str,
    measure: dict[str, Any],
) -> tuple[float | None, str | None, float | None, str | None]:
    numeric_value = to_numeric_value(data_row.get(column))
    unit = normalize_supported_unit_value(measure.get("unit"))
    if numeric_value is None or unit is None:
        return numeric_value, unit, None, None

    normalized_measure = normalize_measure_value(
        measure=canonical_measure,
        value=numeric_value,
        unit=unit,
    )
    return (
        numeric_value,
        unit,
        normalized_measure.normalized_value,
        normalized_measure.normalized_unit,
    )


def canonical_dimension_payload(
    block: PreviewBlock,
    data_row: dict[str, Any],
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "plot_id": None,
        "variety": None,
        "treatment": None,
        "location": None,
    }
    suggestions = block.get("type_suggestions", [])
    if not isinstance(suggestions, list):
        return payload

    for item in suggestions:
        if not isinstance(item, dict):
            continue

        column = item.get("column")
        semantic_role = item.get("semantic_role")
        if not isinstance(column, str) or semantic_role != "dimension":
            continue

        canonical_dimension = normalize_canonical_dimension(item.get("canonical_dimension"))
        if canonical_dimension is None:
            continue

        value = dimension_text_value(data_row.get(column))
        if value is None:
            continue
        payload[canonical_dimension] = value

    return payload


def record_to_staging_insert_row(record: PreparedObservationRow) -> StagingInsertRow:
    return (
        str(record["upload_session_id"]),
        str(record["block_id"]),
        str(record["source_sheet"]),
        int(record["source_row_index"]),
        str(record["source_column"]),
        record.get("observation_date"),
        record.get("plot_id"),
        record.get("variety"),
        record.get("treatment"),
        record.get("location"),
        str(record["variable"]),
        record.get("value"),
        record.get("unit"),
        record.get("normalized_value"),
        str(record["normalized_unit"]) if record.get("normalized_unit") is not None else None,
        str(record["validation_status"]),
        Json(list(record.get("quality_flags") or [])),
        Json(dict(record.get("dimensions_json") or {})),
    )


def mark_commit_failure(
    conn: Connection[Any],
    *,
    upload_id: str,
    preview_json: PreviewPayload,
    error_message: str,
) -> None:
    preview_json["commit_error"] = error_message
    with conn.cursor() as cur:
        cur.execute(
            UPDATE_UPLOAD_FAILURE_SQL,
            (UPLOAD_STATUS_FAILED, Json(preview_json), upload_id),
        )
    conn.commit()

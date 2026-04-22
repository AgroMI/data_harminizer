from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import HTTPException
from psycopg import Cursor
from psycopg.types.json import Json

from backend.app.db import get_conn
from backend.app.services.uploads.common import (
    ALLOWED_COLUMN_TYPES,
    ALLOWED_SEMANTIC_ROLES,
    DEFAULT_BLOCK_ID,
    ColumnEditInput,
    PreviewBlock,
    PreviewPayload,
    normalize_canonical_dimension,
    normalize_canonical_measure,
    normalize_supported_unit_value,
    strip_internal_preview_fields,
)
from etl.semantic_mapping import (
    CANONICAL_DIMENSIONS,
    CANONICAL_MEASURES,
    default_canonical_dimension,
    default_canonical_measure,
    infer_default_semantic_role,
)
from etl.unit_harmonization import infer_default_unit, is_supported_unit_for_measure

SELECT_PREVIEW_SQL = "SELECT preview_json FROM raw.upload_sessions WHERE id = %s"
SELECT_PREVIEW_FOR_UPDATE_SQL = f"{SELECT_PREVIEW_SQL} FOR UPDATE"

UPDATE_PREVIEW_SQL = """
UPDATE raw.upload_sessions
SET preview_json = %s, updated_at = now()
WHERE id = %s
"""


def apply_preview_edits(upload_id: str, edits: list[ColumnEditInput]) -> dict[str, Any]:
    edit_index = build_edit_index(edits)

    with get_conn() as conn:
        with conn.cursor() as cur:
            preview_json = fetch_preview(cur, upload_id, for_update=True)
            ensure_preview_mapping_defaults(preview_json)
            apply_column_edits(preview_json, edit_index)
            ensure_preview_mapping_defaults(preview_json)
            validate_preview_semantics(preview_json)
            cur.execute(UPDATE_PREVIEW_SQL, (Json(preview_json), upload_id))
        conn.commit()

    return {"id": upload_id, "preview": strip_internal_preview_fields(preview_json)}


def fetch_preview(cur: Cursor[Any], upload_id: str, *, for_update: bool) -> PreviewPayload:
    sql = SELECT_PREVIEW_FOR_UPDATE_SQL if for_update else SELECT_PREVIEW_SQL
    cur.execute(sql, (upload_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No preview data for upload {upload_id!r} — complete the upload step before fetching preview.")
    loaded_preview = row.get("preview_json") or {}
    return loaded_preview if isinstance(loaded_preview, dict) else {}


def extract_blocks(preview_json: PreviewPayload) -> list[PreviewBlock]:
    blocks = preview_json.get("blocks", [])
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def extract_suggestions(block: PreviewBlock) -> list[dict[str, Any]]:
    suggestions = block.get("type_suggestions", [])
    if not isinstance(suggestions, list):
        return []
    return [item for item in suggestions if isinstance(item, dict)]


def ensure_preview_mapping_defaults(preview_json: PreviewPayload) -> None:
    for block in extract_blocks(preview_json):
        for item in extract_suggestions(block):
            apply_preview_mapping_defaults(item)


def apply_preview_mapping_defaults(item: dict[str, Any]) -> None:
    column = item.get("column")
    suggested = item.get("suggested")
    if not isinstance(column, str) or not isinstance(suggested, str):
        return
    if suggested not in ALLOWED_COLUMN_TYPES:
        return

    warning_list = normalize_warning_list(item.get("warnings"))
    semantic_role = resolve_semantic_role(item=item, column=column, suggested=suggested, warning_list=warning_list)

    item["type_override"] = item.get("type_override")
    item["semantic_role"] = semantic_role
    item["canonical_measure"] = resolve_preview_measure(item, semantic_role, column)
    item["canonical_dimension"] = resolve_preview_dimension(item, semantic_role, column)
    item["unit"] = resolve_preview_unit(item=item, column=column)
    item["warnings"] = warning_list


def normalize_warning_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def resolve_semantic_role(
    *,
    item: dict[str, Any],
    column: str,
    suggested: str,
    warning_list: list[str],
) -> str:
    semantic_role = item.get("semantic_role")
    if isinstance(semantic_role, str) and semantic_role in ALLOWED_SEMANTIC_ROLES:
        return semantic_role
    return infer_default_semantic_role(
        column=column,
        suggested_type=suggested,
        warnings=warning_list,
    )


def resolve_preview_unit(item: dict[str, Any], *, column: str) -> str | None:
    unit = normalize_supported_unit_value(item.get("unit"))
    if unit is not None:
        return unit
    return infer_default_unit(column, item.get("canonical_measure"))


def validate_preview_semantics(preview_json: PreviewPayload) -> None:
    for block in extract_blocks(preview_json):
        validate_block_semantics(block)


def validate_block_semantics(block: PreviewBlock) -> None:
    block_id = str(block.get("block_id") or DEFAULT_BLOCK_ID)
    resolved_types = resolve_final_column_types(block)
    date_columns = 0

    for item in extract_suggestions(block):
        if validate_suggestion_semantics(item, block_id=block_id, resolved_types=resolved_types):
            date_columns += 1

    if date_columns > 1:
        raise HTTPException(
            status_code=422,
            detail=f"Block {block_id} can use at most one date semantic role.",
        )


def validate_suggestion_semantics(
    item: dict[str, Any],
    *,
    block_id: str,
    resolved_types: dict[str, str],
) -> bool:
    column = item.get("column")
    semantic_role = item.get("semantic_role")
    if not isinstance(column, str) or not isinstance(semantic_role, str):
        return False
    if semantic_role not in ALLOWED_SEMANTIC_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid semantic_role for block {block_id}, column {column}.",
        )

    field_values = normalize_semantic_field_values(item)
    final_type = resolved_types.get(column, "text")

    if semantic_role == "measure":
        validate_measure_semantics(
            block_id=block_id,
            column=column,
            final_type=final_type,
            canonical_measure=field_values["canonical_measure"],
            canonical_dimension=field_values["canonical_dimension"],
            unit=field_values["unit"],
        )
        return False
    if semantic_role == "date":
        validate_date_semantics(
            block_id=block_id,
            column=column,
            final_type=final_type,
            canonical_measure=field_values["canonical_measure"],
            canonical_dimension=field_values["canonical_dimension"],
            unit=field_values["unit"],
        )
        return True
    if semantic_role == "dimension":
        validate_dimension_semantics(
            block_id=block_id,
            column=column,
            canonical_measure=field_values["canonical_measure"],
            canonical_dimension=field_values["canonical_dimension"],
            unit=field_values["unit"],
        )
        return False

    validate_ignore_semantics(
        block_id=block_id,
        column=column,
        canonical_measure=field_values["canonical_measure"],
        canonical_dimension=field_values["canonical_dimension"],
        unit=field_values["unit"],
    )
    return False


def normalize_semantic_field_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_measure": normalize_canonical_measure(item.get("canonical_measure")),
        "canonical_dimension": normalize_canonical_dimension(item.get("canonical_dimension")),
        "unit": normalize_supported_unit_value(item.get("unit")),
    }


def validate_measure_semantics(
    *,
    block_id: str,
    column: str,
    final_type: str,
    canonical_measure: str | None,
    canonical_dimension: str | None,
    unit: str | None,
) -> None:
    if final_type != "numeric":
        raise HTTPException(
            status_code=422,
            detail=f"Measure column {column} in block {block_id} must resolve to numeric type.",
        )
    if canonical_measure is None:
        supported = ", ".join(CANONICAL_MEASURES)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Measure column {column} in block {block_id} must select a supported canonical_measure "
                f"({supported})."
            ),
        )
    if canonical_dimension is not None:
        raise HTTPException(
            status_code=422,
            detail=f"canonical_dimension is not allowed for measure column {column} in block {block_id}.",
        )
    if unit is None:
        raise HTTPException(
            status_code=422,
            detail=f"Measure column {column} in block {block_id} must select a supported source unit.",
        )
    if not is_supported_unit_for_measure(canonical_measure, unit):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unit {unit!r} is not supported for canonical measure {canonical_measure} "
                f"in block {block_id}, column {column}."
            ),
        )


def validate_date_semantics(
    *,
    block_id: str,
    column: str,
    final_type: str,
    canonical_measure: str | None,
    canonical_dimension: str | None,
    unit: str | None,
) -> None:
    if final_type != "date":
        raise HTTPException(
            status_code=422,
            detail=f"Date column {column} in block {block_id} must resolve to date type.",
        )
    if canonical_measure is not None or canonical_dimension is not None or unit is not None:
        raise HTTPException(
            status_code=422,
            detail=f"Date column {column} in block {block_id} cannot carry measure or dimension metadata.",
        )


def validate_dimension_semantics(
    *,
    block_id: str,
    column: str,
    canonical_measure: str | None,
    canonical_dimension: str | None,
    unit: str | None,
) -> None:
    if canonical_dimension is None:
        supported = ", ".join(CANONICAL_DIMENSIONS)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Dimension column {column} in block {block_id} must select a supported "
                f"canonical_dimension ({supported})."
            ),
        )
    if canonical_measure is not None or unit is not None:
        raise HTTPException(
            status_code=422,
            detail=f"Dimension column {column} in block {block_id} cannot carry measure metadata.",
        )


def validate_ignore_semantics(
    *,
    block_id: str,
    column: str,
    canonical_measure: str | None,
    canonical_dimension: str | None,
    unit: str | None,
) -> None:
    if canonical_measure is not None or canonical_dimension is not None or unit is not None:
        raise HTTPException(
            status_code=422,
            detail=f"Ignore column {column} in block {block_id} cannot carry semantic metadata.",
        )


def build_edit_index(edits: list[ColumnEditInput]) -> dict[str, dict[str, ColumnEditInput]]:
    index: dict[str, dict[str, ColumnEditInput]] = defaultdict(dict)
    for item in edits:
        if not item.block_id or not item.column:
            continue
        index[item.block_id][item.column] = item
    return index


def apply_column_edits(
    preview_json: PreviewPayload,
    edit_index: dict[str, dict[str, ColumnEditInput]],
) -> None:
    for block in extract_blocks(preview_json):
        block_id = block.get("block_id")
        if not isinstance(block_id, str):
            continue

        block_edits = edit_index.get(block_id)
        if not block_edits:
            continue

        for suggestion in extract_suggestions(block):
            apply_suggestion_edit(suggestion, block_edits)


def apply_suggestion_edit(
    suggestion: dict[str, Any],
    block_edits: dict[str, ColumnEditInput],
) -> None:
    column = suggestion.get("column")
    if not isinstance(column, str):
        return

    edit = block_edits.get(column)
    if edit is None:
        return

    suggestion["type_override"] = edit.type_override
    suggestion["semantic_role"] = edit.semantic_role
    suggestion["canonical_measure"] = edit.canonical_measure
    suggestion["canonical_dimension"] = edit.canonical_dimension
    suggestion["unit"] = edit.unit


def resolve_final_column_types(block: PreviewBlock) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for item in extract_suggestions(block):
        column = item.get("column")
        if not isinstance(column, str):
            continue

        resolved_type = resolve_suggestion_type(item)
        if resolved_type is not None:
            resolved[column] = resolved_type

    return resolved


def resolve_suggestion_type(item: dict[str, Any]) -> str | None:
    type_override = item.get("type_override")
    suggested = item.get("suggested")

    if isinstance(type_override, str) and type_override in ALLOWED_COLUMN_TYPES:
        return type_override
    if isinstance(suggested, str) and suggested in ALLOWED_COLUMN_TYPES:
        return suggested
    return None

def resolve_preview_measure(
    item: dict[str, Any],
    semantic_role: str,
    column: str,
) -> str | None:
    canonical_measure = normalize_canonical_measure(item.get("canonical_measure"))
    if canonical_measure is not None:
        return canonical_measure
    return default_canonical_measure(semantic_role, column)


def resolve_preview_dimension(
    item: dict[str, Any],
    semantic_role: str,
    column: str,
) -> str | None:
    canonical_dimension = normalize_canonical_dimension(item.get("canonical_dimension"))
    if canonical_dimension is not None:
        return canonical_dimension
    return default_canonical_dimension(semantic_role, column)

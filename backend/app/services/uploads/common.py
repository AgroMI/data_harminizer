from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from psycopg.types.json import Json

from etl.semantic_mapping import CANONICAL_DIMENSIONS, CANONICAL_MEASURES
from etl.types import (
    CanonicalDimension,
    CanonicalMeasure,
    ColumnType,
    QualityFlag,
    SemanticRole,
    SupportedUnit,
    ValidationStatus,
)
from etl.unit_harmonization import normalize_supported_unit

UPLOAD_STATUS_PREVIEW_READY = "preview_ready"
UPLOAD_STATUS_COMMITTED = "committed"
UPLOAD_STATUS_FAILED = "failed"
DEFAULT_UPLOADER_USER_ID = "placeholder-uploader"
DEFAULT_BLOCK_ID = "S1_B1"
DEFAULT_SOURCE_SHEET = "unknown"
DEFAULT_STORAGE_TYPE = "db_bytea"

ALLOWED_COLUMN_TYPES: set[ColumnType] = {"text", "numeric", "date"}
ALLOWED_SEMANTIC_ROLES: set[SemanticRole] = {"ignore", "date", "dimension", "measure"}
ALLOWED_CANONICAL_DIMENSIONS: set[CanonicalDimension] = set(CANONICAL_DIMENSIONS)
ALLOWED_CANONICAL_MEASURES: set[CanonicalMeasure] = set(CANONICAL_MEASURES)

PreviewPayload = dict[str, Any]
PreviewBlock = dict[str, Any]
PreparedObservationRow = dict[str, Any]
StagingInsertRow = tuple[
    str,
    str,
    str,
    int,
    str,
    date | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str,
    float | None,
    SupportedUnit | None,
    float | None,
    str | None,
    str,
    Json,
    Json,
]


@dataclass(frozen=True, slots=True)
class ColumnEditInput:
    block_id: str
    column: str
    type_override: ColumnType | None
    semantic_role: SemanticRole
    canonical_measure: CanonicalMeasure | None
    canonical_dimension: CanonicalDimension | None
    unit: SupportedUnit | None


@dataclass(frozen=True, slots=True)
class CommitResult:
    id: str
    status: str
    staging_rows: int
    harmonized_rows: int


def strip_internal_preview_fields(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: strip_internal_preview_fields(value)
            for key, value in payload.items()
            if not key.startswith("_")
        }

    if isinstance(payload, list):
        return [strip_internal_preview_fields(item) for item in payload]

    return payload


def sha256_hex(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def normalize_canonical_measure(value: Any) -> CanonicalMeasure | None:
    cleaned = normalize_optional_text(value)
    if cleaned is None or cleaned not in ALLOWED_CANONICAL_MEASURES:
        return None
    return cleaned


def normalize_canonical_dimension(value: Any) -> CanonicalDimension | None:
    cleaned = normalize_optional_text(value)
    if cleaned is None or cleaned not in ALLOWED_CANONICAL_DIMENSIONS:
        return None
    return cleaned


def normalize_supported_unit_value(value: Any) -> SupportedUnit | None:
    if value is None:
        return None
    return normalize_supported_unit(str(value))


def json_primitive(value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return str(value)


def dimension_text_value(value: Any) -> str | None:
    primitive = json_primitive(value)
    if primitive is None:
        return None
    return str(primitive)

from __future__ import annotations

from typing import Any

from backend.app.retrieval.retrieval_sources import (
    CANONICAL_DIMENSION_DESCRIPTIONS,
    CANONICAL_MEASURE_DESCRIPTIONS,
    QUALITY_FLAG_DESCRIPTIONS,
    VALIDATION_STATUS_DESCRIPTIONS,
)
from etl.semantic_mapping import (
    CANONICAL_DATE,
    CANONICAL_DIMENSIONS,
    CANONICAL_MEASURES,
    DIMENSION_TOKEN_MAP,
    MEASURE_TOKEN_MAP,
)
from etl.unit_harmonization import CANONICAL_UNIT_BY_MEASURE

SAFE_RELATION_NAME = "safe.harmonized_observations_v1"
DEFAULT_RECORD_LIMIT = 25
MAX_RECORD_LIMIT = 200
SQL_EXECUTION_TIMEOUT_MS = 2500

SAFE_COLUMNS: tuple[dict[str, str], ...] = (
    {"name": "upload_session_id", "type": "text", "role": "scope"},
    {"name": CANONICAL_DATE, "type": "date", "role": "time"},
    {"name": "plot_id", "type": "text", "role": "dimension"},
    {"name": "variety", "type": "text", "role": "dimension"},
    {"name": "treatment", "type": "text", "role": "dimension"},
    {"name": "location", "type": "text", "role": "dimension"},
    {"name": "variable", "type": "text", "role": "measure_selector"},
    {"name": "value", "type": "numeric", "role": "raw_measure"},
    {"name": "unit", "type": "text", "role": "raw_unit"},
    {"name": "normalized_value", "type": "numeric", "role": "canonical_measure"},
    {"name": "normalized_unit", "type": "text", "role": "canonical_unit"},
    {"name": "validation_status", "type": "text", "role": "quality_status"},
    {"name": "quality_flags", "type": "jsonb", "role": "quality_flags"},
)

SAFE_PROJECTION_COLUMNS: tuple[str, ...] = (
    "upload_session_id",
    "observation_date",
    "plot_id",
    "variety",
    "treatment",
    "location",
    "variable",
    "value",
    "unit",
    "normalized_value",
    "normalized_unit",
    "validation_status",
    "quality_flags",
)

SAFE_FILTER_FIELDS: tuple[str, ...] = (
    "upload_session_id",
    "observation_date",
    "plot_id",
    "variety",
    "treatment",
    "location",
    "variable",
    "normalized_unit",
    "validation_status",
)

SAFE_GROUP_FIELDS: tuple[str, ...] = (
    "plot_id",
    "variety",
    "treatment",
    "location",
    "validation_status",
)

FORBIDDEN_REQUEST_TERMS: tuple[str, ...] = (
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "truncate",
    "pg_catalog",
    "information_schema",
    "source_row_index",
    "source_column",
    "source_sheet",
    "raw_content",
    "dump",
)


def build_schema_snapshot(query_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "safe_relations": [
            {
                "relation_name": SAFE_RELATION_NAME,
                "description": (
                    "Read-only safe view over harmonized agricultural observations. "
                    "Only canonical dimensions, canonical measures, units and quality fields are exposed."
                ),
                "columns": list(SAFE_COLUMNS),
            }
        ],
        "canonical_dimensions": [
            {
                "name": dimension,
                "description": CANONICAL_DIMENSION_DESCRIPTIONS[dimension],
                "aliases": list(DIMENSION_TOKEN_MAP[dimension]),
            }
            for dimension in CANONICAL_DIMENSIONS
        ],
        "canonical_measures": [
            {
                "name": measure,
                "description": CANONICAL_MEASURE_DESCRIPTIONS[measure],
                "aliases": list(MEASURE_TOKEN_MAP[measure]),
                "canonical_unit": CANONICAL_UNIT_BY_MEASURE[measure],
            }
            for measure in CANONICAL_MEASURES
        ],
        "validation_statuses": VALIDATION_STATUS_DESCRIPTIONS,
        "quality_flags": QUALITY_FLAG_DESCRIPTIONS,
        "query_metadata": query_metadata,
        "limits": {
            "default_limit": DEFAULT_RECORD_LIMIT,
            "max_limit": MAX_RECORD_LIMIT,
            "timeout_ms": SQL_EXECUTION_TIMEOUT_MS,
        },
    }

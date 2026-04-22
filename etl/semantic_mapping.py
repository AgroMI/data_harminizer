from typing import Iterable

from etl.types import (
    CanonicalDimension,
    CanonicalMeasure,
    ColumnType,
    ColumnWarningCode,
    SemanticRole,
)

CANONICAL_DIMENSIONS: tuple[CanonicalDimension, ...] = (
    "plot_id",
    "variety",
    "treatment",
    "location",
)
CANONICAL_MEASURES: tuple[CanonicalMeasure, ...] = (
    "yield",
    "moisture",
    "plant_height",
)
CANONICAL_DATE = "observation_date"

DATE_TOKENS = ("date", "day", "time", "timestamp", "harvest_date", "sampling_date")

DIMENSION_TOKEN_MAP: dict[CanonicalDimension, tuple[str, ...]] = {
    "plot_id": ("plot_id", "plot", "parcel", "parcela", "plotcode", "plot_code"),
    "variety": ("variety", "cultivar", "genotype", "hybrid"),
    "treatment": ("treatment", "treat", "trt", "fert", "fertilizer", "nitrogen"),
    "location": ("location", "site", "station", "field", "farm"),
}

MEASURE_TOKEN_MAP: dict[CanonicalMeasure, tuple[str, ...]] = {
    "yield": (
        "yield",
        "grain_yield",
        "yield_kg_ha",
        "yield_t_ha",
        "kg_ha",
        "t_ha",
        "parcellatermes",
        "termes",
    ),
    "moisture": ("moisture", "humidity", "moisture_pct", "moisture_percent", "pct"),
    "plant_height": ("plant_height", "height", "plantheight", "height_cm"),
}


def _normalize_column_key(column: str) -> str:
    return column.strip().lower()


def infer_default_canonical_dimension(column: str) -> CanonicalDimension | None:
    normalized = _normalize_column_key(column)
    for canonical, tokens in DIMENSION_TOKEN_MAP.items():
        if normalized == canonical or any(token in normalized for token in tokens):
            return canonical
    return None


def infer_default_canonical_measure(column: str) -> CanonicalMeasure | None:
    normalized = _normalize_column_key(column)
    for canonical, tokens in MEASURE_TOKEN_MAP.items():
        if normalized == canonical or any(token in normalized for token in tokens):
            return canonical
    return None


def infer_default_semantic_role(
    *,
    column: str,
    suggested_type: ColumnType,
    warnings: Iterable[ColumnWarningCode] | None = None,
) -> SemanticRole:
    warning_set = set(warnings or [])
    normalized = _normalize_column_key(column)

    if suggested_type == "date" or any(token in normalized for token in DATE_TOKENS):
        return "date"

    if column.startswith("column_") or "annotation_like" in warning_set:
        if infer_default_canonical_dimension(column) is None:
            return "ignore"

    if infer_default_canonical_dimension(column) is not None:
        return "dimension"

    if suggested_type == "numeric" or infer_default_canonical_measure(column) is not None:
        return "measure"

    return "ignore"


def default_canonical_measure(role: SemanticRole, column: str) -> CanonicalMeasure | None:
    if role == "measure":
        return infer_default_canonical_measure(column)
    return None


def default_canonical_dimension(role: SemanticRole, column: str) -> CanonicalDimension | None:
    if role == "dimension":
        return infer_default_canonical_dimension(column)
    return None

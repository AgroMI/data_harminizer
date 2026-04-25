import re
from typing import Any, Iterable

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
    "replicate",
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
    "replicate": ("replicate", "rep_", "_rep", "ismétlés", "ismetles", "block_id", "block"),
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
        "sza",
    ),
    "moisture": ("moisture", "humidity", "moisture_pct", "moisture_percent", "pct", "viz", "víz"),
    "plant_height": ("plant_height", "height", "plantheight", "height_cm"),
}

# Roman numeral replicate labels commonly used in Hungarian agrarian trials
_ROMAN_REPLICATE_VALUES = frozenset(
    "i. ii. iii. iv. v. vi. vii. viii. ix. x.".split()
)

# Pattern for nitrogen-level column names like n_0, n_40, n_80, n_0_a, n_40_b
_N_LEVEL_PATTERN = re.compile(r"^n_\d+")
_TREATMENT_VALUE_HINTS = ("n0", "n 0", "n40", "n 40", "n80", "n 80", "n120", "n 120", "trágya", "tragya")
_VARIETY_VALUE_HINTS = (" mv ", " my ", " cultivar", " variety", " hybrid")


def _normalize_column_key(column: str) -> str:
    return column.strip().lower()


def _values_are_replicate_labels(values: list[Any]) -> bool:
    """Return True when all non-empty values look like roman-numeral replicate labels."""
    non_empty = [str(v).strip().lower() for v in values if v is not None and str(v).strip()]
    if not non_empty:
        return False
    unique = set(non_empty)
    return len(unique) <= 12 and unique.issubset(_ROMAN_REPLICATE_VALUES)


def _values_are_treatment_labels(values: list[Any]) -> bool:
    non_empty = [str(v).strip().lower() for v in values if v is not None and str(v).strip()]
    if len(non_empty) < 2:
        return False
    return any(any(hint in value for hint in _TREATMENT_VALUE_HINTS) for value in non_empty)


def _values_are_variety_labels(values: list[Any]) -> bool:
    non_empty = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not non_empty:
        return False

    normalized = [value.lower() for value in non_empty]

    if any(any(hint in f" {value} " for hint in _VARIETY_VALUE_HINTS) for value in normalized):
        return True

    # Fallback: numbered cultivar-like labels such as "1. Mv Toborzó"
    numbered_ratio = sum(1 for value in normalized if re.match(r"^\d+\.\s+\S+", value)) / len(normalized)
    if numbered_ratio >= 0.5:
        return True

    unique = set(normalized)
    return len(unique) >= 2


def infer_default_canonical_dimension(
    column: str,
    *,
    values: list[Any] | None = None,
) -> CanonicalDimension | None:
    normalized = _normalize_column_key(column)
    for canonical, tokens in DIMENSION_TOKEN_MAP.items():
        if normalized == canonical or any(token in normalized for token in tokens):
            return canonical
    if values is not None and _values_are_replicate_labels(values):
        return "replicate"
    if values is not None and _values_are_treatment_labels(values):
        return "treatment"
    if values is not None and _values_are_variety_labels(values):
        return "variety"
    return None


def infer_default_canonical_measure(column: str) -> CanonicalMeasure | None:
    normalized = _normalize_column_key(column)
    for canonical, tokens in MEASURE_TOKEN_MAP.items():
        if normalized == canonical or any(token in normalized for token in tokens):
            return canonical
    # N-level trial columns (n_0_a, n_40_b …) are yield measurements
    if _N_LEVEL_PATTERN.match(normalized):
        return "yield"
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

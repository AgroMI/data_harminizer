from collections import defaultdict
from typing import Any, MutableMapping

from etl.types import CanonicalMeasure, QualityFlag, ValidationStatus

INVALID_FLAGS: set[QualityFlag] = {
    "missing_required_dimension",
    "missing_observation_date",
    "missing_unit",
    "missing_measure_value",
}

OUTLIER_RANGES: dict[CanonicalMeasure, tuple[float, float]] = {
    "yield": (0.0, 25000.0),
    "moisture": (0.0, 100.0),
    "plant_height": (0.0, 500.0),
}

DIMENSION_KEYS = ("plot_id", "variety", "treatment", "location")


def _append_flag(record: MutableMapping[str, Any], flag: QualityFlag) -> None:
    flags = record.setdefault("quality_flags", [])
    if flag not in flags:
        flags.append(flag)


def _resolve_validation_status(flags: list[QualityFlag]) -> ValidationStatus:
    if any(flag in INVALID_FLAGS for flag in flags):
        return "invalid"
    if flags:
        return "warning"
    return "valid"


def validate_observation_records(records: list[MutableMapping[str, Any]]) -> None:
    duplicate_groups: dict[tuple[Any, ...], list[MutableMapping[str, Any]]] = defaultdict(list)

    for record in records:
        record["quality_flags"] = list(record.get("quality_flags") or [])

        if record.get("value") is None and record.get("normalized_value") is None:
            _append_flag(record, "missing_measure_value")

        if record.get("unit") is None or record.get("normalized_unit") is None:
            _append_flag(record, "missing_unit")

        if record.get("_requires_observation_date") and record.get("observation_date") is None:
            _append_flag(record, "missing_observation_date")

        if not any(record.get(key) for key in DIMENSION_KEYS):
            _append_flag(record, "missing_required_dimension")

        variable = record.get("variable")
        normalized_value = record.get("normalized_value")
        if isinstance(variable, str) and isinstance(normalized_value, (int, float)) and variable in OUTLIER_RANGES:
            lower, upper = OUTLIER_RANGES[variable]  # type: ignore[index]
            if normalized_value < lower or normalized_value > upper:
                _append_flag(record, "outlier_candidate")

        duplicate_key = (
            record.get("upload_session_id"),
            record.get("source_sheet"),
            record.get("observation_date"),
            record.get("plot_id"),
            record.get("variety"),
            record.get("treatment"),
            record.get("location"),
            record.get("variable"),
        )
        duplicate_groups[duplicate_key].append(record)

    for group_records in duplicate_groups.values():
        if len(group_records) < 2:
            continue
        for record in group_records:
            _append_flag(record, "duplicate_candidate")

    for record in records:
        flags = [flag for flag in record.get("quality_flags", []) if isinstance(flag, str)]
        record["quality_flags"] = flags
        record["validation_status"] = _resolve_validation_status(flags)

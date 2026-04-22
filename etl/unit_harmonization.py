from dataclasses import dataclass

from etl.types import CanonicalMeasure, CanonicalUnit, SupportedUnit

SUPPORTED_UNITS: tuple[SupportedUnit, ...] = ("kg/ha", "t/ha", "%", "cm", "m")

CANONICAL_UNIT_BY_MEASURE: dict[CanonicalMeasure, CanonicalUnit] = {
    "yield": "kg/ha",
    "moisture": "%",
    "plant_height": "cm",
}

SUPPORTED_UNITS_BY_MEASURE: dict[CanonicalMeasure, tuple[SupportedUnit, ...]] = {
    "yield": ("kg/ha", "t/ha"),
    "moisture": ("%",),
    "plant_height": ("cm", "m"),
}

UNIT_TOKEN_MAP: dict[CanonicalMeasure, dict[SupportedUnit, tuple[str, ...]]] = {
    "yield": {
        "kg/ha": ("kg_ha", "kg/ha"),
        "t/ha": ("t_ha", "t/ha"),
    },
    "moisture": {
        "%": ("pct", "%", "percent"),
    },
    "plant_height": {
        "cm": ("height_cm", "_cm", " cm"),
        "m": ("height_m", "_m", " m"),
    },
}


@dataclass(frozen=True, slots=True)
class NormalizedMeasureValue:
    source_value: float
    source_unit: SupportedUnit
    normalized_value: float
    normalized_unit: CanonicalUnit


def normalize_supported_unit(value: str | None) -> SupportedUnit | None:
    if value is None:
        return None

    cleaned = str(value).strip().lower()
    if not cleaned:
        return None

    alias_map: dict[str, SupportedUnit] = {
        "kg/ha": "kg/ha",
        "kg_ha": "kg/ha",
        "t/ha": "t/ha",
        "t_ha": "t/ha",
        "%": "%",
        "pct": "%",
        "percent": "%",
        "cm": "cm",
        "m": "m",
    }
    return alias_map.get(cleaned)


def canonical_unit_for_measure(measure: CanonicalMeasure) -> CanonicalUnit:
    return CANONICAL_UNIT_BY_MEASURE[measure]


def supported_units_for_measure(measure: CanonicalMeasure) -> tuple[SupportedUnit, ...]:
    return SUPPORTED_UNITS_BY_MEASURE[measure]


def is_supported_unit_for_measure(measure: CanonicalMeasure, unit: str | None) -> bool:
    normalized = normalize_supported_unit(unit)
    if normalized is None:
        return False
    return normalized in SUPPORTED_UNITS_BY_MEASURE[measure]


def infer_default_unit(column: str, measure: CanonicalMeasure | None) -> SupportedUnit | None:
    if measure is None:
        return None

    normalized = column.strip().lower()
    for unit, tokens in UNIT_TOKEN_MAP[measure].items():
        if any(token in normalized for token in tokens):
            return unit

    supported_units = SUPPORTED_UNITS_BY_MEASURE[measure]
    if len(supported_units) == 1:
        return supported_units[0]
    return None


def normalize_measure_value(
    *,
    measure: CanonicalMeasure,
    value: float,
    unit: SupportedUnit,
) -> NormalizedMeasureValue:
    if measure == "yield":
        if unit == "kg/ha":
            normalized_value = value
        elif unit == "t/ha":
            normalized_value = value * 1000.0
        else:
            raise ValueError(f"Unsupported unit {unit} for yield.")
    elif measure == "moisture":
        if unit != "%":
            raise ValueError(f"Unsupported unit {unit} for moisture.")
        normalized_value = value
    elif measure == "plant_height":
        if unit == "cm":
            normalized_value = value
        elif unit == "m":
            normalized_value = value * 100.0
        else:
            raise ValueError(f"Unsupported unit {unit} for plant_height.")
    else:  # pragma: no cover - defensive branch for future measures
        raise ValueError(f"Unsupported canonical measure {measure}.")

    return NormalizedMeasureValue(
        source_value=value,
        source_unit=unit,
        normalized_value=round(normalized_value, 6),
        normalized_unit=CANONICAL_UNIT_BY_MEASURE[measure],
    )

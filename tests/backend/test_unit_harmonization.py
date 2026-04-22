from __future__ import annotations

from etl.unit_harmonization import (
    canonical_unit_for_measure,
    infer_default_unit,
    is_supported_unit_for_measure,
    normalize_measure_value,
)


def test_t_ha_to_kg_ha_conversion() -> None:
    result = normalize_measure_value(measure="yield", value=12.5, unit="t/ha")

    assert result.source_value == 12.5
    assert result.source_unit == "t/ha"
    assert result.normalized_value == 12500.0
    assert result.normalized_unit == "kg/ha"


def test_m_to_cm_conversion() -> None:
    result = normalize_measure_value(measure="plant_height", value=1.12, unit="m")

    assert result.normalized_value == 112.0
    assert result.normalized_unit == "cm"


def test_percent_identity_conversion() -> None:
    result = normalize_measure_value(measure="moisture", value=17.2, unit="%")

    assert result.normalized_value == 17.2
    assert result.normalized_unit == "%"


def test_measure_unit_support_matrix() -> None:
    assert is_supported_unit_for_measure("yield", "kg/ha") is True
    assert is_supported_unit_for_measure("yield", "t/ha") is True
    assert is_supported_unit_for_measure("yield", "cm") is False
    assert canonical_unit_for_measure("plant_height") == "cm"


def test_infer_default_unit_from_column_name() -> None:
    assert infer_default_unit("yield_t_ha", "yield") == "t/ha"
    assert infer_default_unit("yield_kg_ha", "yield") == "kg/ha"
    assert infer_default_unit("plant_height_m", "plant_height") == "m"
    assert infer_default_unit("moisture_pct", "moisture") == "%"
    assert infer_default_unit("moisture", "moisture") == "%"

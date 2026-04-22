from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.tools.tool_types import BaseTool
from etl.types import CanonicalMeasure, SupportedUnit
from etl.unit_harmonization import normalize_measure_value, normalize_supported_unit


class UnitConversionToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_measure: CanonicalMeasure = Field(description="Canonical measure to normalize.")
    source_unit: SupportedUnit = Field(description="Supported source unit for the measure.")
    value: float = Field(description="Numeric source value to normalize.")

    @field_validator("source_unit", mode="before")
    @classmethod
    def normalize_source_unit(cls, value: str | None) -> SupportedUnit | str | None:
        normalized = normalize_supported_unit(value)
        if normalized is None:
            return value
        return normalized


class UnitConversionTool(BaseTool):
    tool_name = "unit_conversion_tool"
    description = "Deterministic read-only unit normalization for a canonical measure."
    category = "conversion"
    input_model = UnitConversionToolArguments

    def execute(self, arguments: UnitConversionToolArguments) -> dict[str, object]:
        converted = normalize_measure_value(
            measure=arguments.canonical_measure,
            value=arguments.value,
            unit=arguments.source_unit,
        )
        return {
            "canonical_measure": arguments.canonical_measure,
            "source_value": converted.source_value,
            "source_unit": converted.source_unit,
            "normalized_value": converted.normalized_value,
            "normalized_unit": converted.normalized_unit,
        }

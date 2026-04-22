from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.harmonized_query_service import (
    SUPPORTED_QUALITY_FLAGS,
    SUPPORTED_VALIDATION_STATUSES,
    get_harmonized_query_metadata,
)
from backend.app.tools.tool_types import BaseTool
from etl.semantic_mapping import CANONICAL_DIMENSIONS, CANONICAL_MEASURES
from etl.unit_harmonization import CANONICAL_UNIT_BY_MEASURE, SUPPORTED_UNITS_BY_MEASURE


class MetadataToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_query_metadata: bool = Field(
        default=True,
        description="Whether the live harmonized query metadata snapshot should be included.",
    )


class MetadataTool(BaseTool):
    tool_name = "metadata_tool"
    description = "Read-only system metadata for canonical catalog, units, validation and query metadata."
    category = "metadata"
    input_model = MetadataToolArguments

    def execute(self, arguments: MetadataToolArguments) -> dict[str, object]:
        result: dict[str, object] = {
            "canonical_variables": list(CANONICAL_MEASURES),
            "canonical_dimensions": list(CANONICAL_DIMENSIONS),
            "canonical_units_by_measure": dict(CANONICAL_UNIT_BY_MEASURE),
            "supported_units_by_measure": {
                measure: list(units)
                for measure, units in SUPPORTED_UNITS_BY_MEASURE.items()
            },
            "validation_statuses": list(SUPPORTED_VALIDATION_STATUSES),
            "quality_flags": list(SUPPORTED_QUALITY_FLAGS),
        }
        if arguments.include_query_metadata:
            result["query_metadata"] = get_harmonized_query_metadata()
        return result

from __future__ import annotations

from datetime import date as DateValue
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas import AggregationGroupBy, AggregationMetric
from backend.app.services.harmonized_query_service import (
    HarmonizedObservationFilters,
    aggregate_harmonized_observations,
    get_harmonized_query_metadata,
    list_harmonized_observations,
)
from backend.app.tools.tool_types import BaseTool
from etl.types import CanonicalMeasure, CanonicalUnit, QualityFlag, ValidationStatus

QueryToolOperation = Literal["list_observations", "aggregate", "query_metadata"]


class QueryToolFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_session_id: str | None = Field(default=None, description="Optional upload/session scope.")
    variable: CanonicalMeasure | None = Field(default=None, description="Canonical measure filter.")
    variety: str | None = Field(default=None, description="Canonical variety filter.")
    location: str | None = Field(default=None, description="Canonical location filter.")
    treatment: str | None = Field(default=None, description="Canonical treatment filter.")
    plot_id: str | None = Field(default=None, description="Canonical plot identifier filter.")
    observation_date_from: DateValue | None = Field(default=None, description="Inclusive lower date bound.")
    observation_date_to: DateValue | None = Field(default=None, description="Inclusive upper date bound.")
    validation_status: ValidationStatus | None = Field(default=None, description="Validation status filter.")
    quality_flag: QualityFlag | None = Field(default=None, description="Quality flag filter.")
    normalized_unit: CanonicalUnit | None = Field(default=None, description="Canonical normalized unit filter.")


class QueryToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: QueryToolOperation = Field(description="Query operation to execute.")
    filters: QueryToolFilters = Field(default_factory=QueryToolFilters, description="Shared read-only query filters.")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum records returned for list operations.")
    group_by: AggregationGroupBy | None = Field(default=None, description="Aggregation group-by field for aggregate operation.")
    metric: AggregationMetric | None = Field(default=None, description="Aggregation metric for aggregate operation.")
    include_invalid: bool = Field(default=False, description="Whether aggregation may include invalid rows.")

    @model_validator(mode="after")
    def validate_operation_specific_fields(self) -> "QueryToolArguments":
        if self.operation == "aggregate":
            if self.group_by is None:
                raise ValueError("group_by is required for aggregate operation.")
            if self.metric is None:
                raise ValueError("metric is required for aggregate operation.")
        return self


class QueryTool(BaseTool):
    tool_name = "query_tool"
    description = "Read-only access to harmonized observations, aggregations and query metadata."
    category = "query"
    input_model = QueryToolArguments

    def execute(self, arguments: QueryToolArguments) -> dict[str, object]:
        if arguments.operation == "query_metadata":
            return get_harmonized_query_metadata()

        filters = HarmonizedObservationFilters(
            upload_session_id=arguments.filters.upload_session_id,
            variable=arguments.filters.variable,
            variety=arguments.filters.variety,
            location=arguments.filters.location,
            treatment=arguments.filters.treatment,
            plot_id=arguments.filters.plot_id,
            observation_date_from=arguments.filters.observation_date_from,
            observation_date_to=arguments.filters.observation_date_to,
            validation_status=arguments.filters.validation_status,
            quality_flag=arguments.filters.quality_flag,
            normalized_unit=arguments.filters.normalized_unit,
        )

        if arguments.operation == "list_observations":
            return list_harmonized_observations(limit=arguments.limit, filters=filters)

        return aggregate_harmonized_observations(
            group_by=arguments.group_by,  # type: ignore[arg-type]
            metric=arguments.metric,  # type: ignore[arg-type]
            filters=filters,
            include_invalid=arguments.include_invalid,
        )

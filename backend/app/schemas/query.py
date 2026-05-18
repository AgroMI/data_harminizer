from __future__ import annotations

from datetime import date as DateValue

from pydantic import BaseModel, Field

from backend.app.schemas.common import AggregationGroupBy, AggregationMetric
from etl.types import CanonicalUnit, QualityFlag, SupportedUnit, ValidationStatus


class HarmonizedObservationListItem(BaseModel):
    upload_session_id: str
    observation_date: DateValue | None = None
    plot_id: str | None = None
    variety: str | None = None
    treatment: str | None = None
    location: str | None = None
    replicate: str | None = None
    variable: str | None = None
    value: float | None = None
    unit: SupportedUnit | None = None
    normalized_value: float | None = None
    normalized_unit: CanonicalUnit | None = None
    validation_status: ValidationStatus
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    block_id: str
    source_sheet: str
    source_row_index: int
    source_column: str


class HarmonizedObservationListResponse(BaseModel):
    items: list[HarmonizedObservationListItem]
    count: int = Field(ge=0)


class HarmonizedAggregationItem(BaseModel):
    group_value: str | None = None
    metric_value: float | int
    record_count: int = Field(ge=0)
    normalized_unit: CanonicalUnit | None = None


class HarmonizedAggregationResponse(BaseModel):
    group_by: AggregationGroupBy
    metric: AggregationMetric
    include_invalid: bool
    items: list[HarmonizedAggregationItem]
    count: int = Field(ge=0)


class HarmonizedQueryMetadataResponse(BaseModel):
    supported_filters: list[str] = Field(default_factory=list)
    supported_group_bys: list[AggregationGroupBy] = Field(default_factory=list)
    supported_metrics: list[AggregationMetric] = Field(default_factory=list)
    supported_validation_statuses: list[ValidationStatus] = Field(default_factory=list)
    supported_quality_flags: list[QualityFlag] = Field(default_factory=list)
    available_variables: list[str] = Field(default_factory=list)
    available_normalized_units: list[CanonicalUnit] = Field(default_factory=list)
    available_varieties: list[str] = Field(default_factory=list)
    available_locations: list[str] = Field(default_factory=list)
    available_treatments: list[str] = Field(default_factory=list)
    available_plot_ids: list[str] = Field(default_factory=list)
    available_validation_statuses: list[ValidationStatus] = Field(default_factory=list)
    available_quality_flags: list[QualityFlag] = Field(default_factory=list)
    aggregations_exclude_invalid_by_default: bool

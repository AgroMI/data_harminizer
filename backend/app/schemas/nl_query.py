from __future__ import annotations

from datetime import date as DateValue

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import (
    AggregationGroupBy,
    AggregationMetric,
    NLQueryIntentType,
    NLQueryResultType,
)
from backend.app.schemas.query import (
    HarmonizedAggregationItem,
    HarmonizedObservationListItem,
)
from etl.types import CanonicalMeasure, CanonicalUnit, QualityFlag, ValidationStatus


class NLQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)


class NLQueryPlanFilters(BaseModel):
    upload_session_id: str | None = None
    variable: CanonicalMeasure | None = None
    variety: str | None = None
    location: str | None = None
    treatment: str | None = None
    plot_id: str | None = None
    observation_date_from: DateValue | None = None
    observation_date_to: DateValue | None = None
    validation_status: ValidationStatus | None = None
    validation_statuses: list[ValidationStatus] = Field(default_factory=list)
    quality_flag: QualityFlag | None = None
    normalized_unit: CanonicalUnit | None = None


class NLQueryPlan(BaseModel):
    intent_type: NLQueryIntentType
    variable: CanonicalMeasure | None = None
    group_by: AggregationGroupBy | None = None
    metric: AggregationMetric | None = None
    filters: NLQueryPlanFilters = Field(default_factory=NLQueryPlanFilters)
    include_invalid: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    top_k: int | None = Field(default=None, ge=1, le=20)


class NLQueryResultPayload(BaseModel):
    records: list[HarmonizedObservationListItem] = Field(default_factory=list)
    aggregations: list[HarmonizedAggregationItem] = Field(default_factory=list)
    top_group: HarmonizedAggregationItem | None = None
    count: int = Field(default=0, ge=0)


class NLQueryResponse(BaseModel):
    question: str
    supported: bool
    recognized_intent: NLQueryIntentType
    query_plan: NLQueryPlan
    result_type: NLQueryResultType
    results: NLQueryResultPayload
    explanation: str

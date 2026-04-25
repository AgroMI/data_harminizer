from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.llm.types import PipelineMode, PlanningMetadata
from etl.types import CanonicalDimension, CanonicalMeasure, CanonicalUnit

TextToSqlPlanStatus = Literal["supported", "unsupported", "clarification_required"]
TextToSqlIntent = Literal["select_records", "aggregate", "unsupported", "clarification_required"]
QueryFilterOperator = Literal["eq", "ilike", "gte", "lte", "in"]
AggregationFunction = Literal["avg", "count"]
OrderingDirection = Literal["asc", "desc"]
UnitHandlingMode = Literal["canonical_normalized", "none"]
PipelineResultType = Literal["records", "aggregation", "unsupported"]
QueryDimensionField = Literal["plot_id", "variety", "treatment", "location", "validation_status"]


class QueryFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    operator: QueryFilterOperator
    value: object
    source_text: str | None = None


class QueryAggregation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: AggregationFunction
    field_name: str = Field(min_length=1)
    alias: str = Field(min_length=1)


class QueryOrdering(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1)
    direction: OrderingDirection
    source_text: str | None = None


class UnitHandling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: UnitHandlingMode
    normalized_unit: CanonicalUnit | None = None
    note: str | None = None


class QueryTraceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_text: str = Field(min_length=1)
    mapped_to: str = Field(min_length=1)
    note: str | None = None


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TextToSqlPlanStatus
    intent: TextToSqlIntent
    source_relation: str = Field(min_length=1)
    selected_measures: list[CanonicalMeasure] = Field(default_factory=list)
    selected_dimensions: list[QueryDimensionField] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    aggregations: list[QueryAggregation] = Field(default_factory=list)
    grouping: list[QueryDimensionField] = Field(default_factory=list)
    ordering: list[QueryOrdering] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=200)
    unit_handling: UnitHandling = Field(default_factory=lambda: UnitHandling(mode="none"))
    ambiguity_flags: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    trace: list[QueryTraceItem] = Field(default_factory=list)
    target_measure: CanonicalMeasure | None = None
    result_type: PipelineResultType = "unsupported"

    @property
    def supported(self) -> bool:
        return self.status == "supported"


class GeneratedSql(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1)
    parameters: list[object] = Field(default_factory=list)
    relation_names: list[str] = Field(default_factory=list)
    projected_columns: list[str] = Field(default_factory=list)


class SqlValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: Literal["error", "warning"] = "error"


class SqlValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    normalized_sql: str | None = None
    enforced_limit: int | None = None
    relation_names: list[str] = Field(default_factory=list)
    issues: list[SqlValidationIssue] = Field(default_factory=list)


class SqlExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    duration_ms: int = Field(default=0, ge=0)


class ToolTraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    success: bool
    error_code: str | None = None
    duration_ms: int | None = None


class TextToSqlPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    upload_session_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=200)
    explain: bool = True
    mode: PipelineMode = "deterministic"


class TextToSqlPipelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    question: str
    status: TextToSqlPlanStatus
    result_type: PipelineResultType
    query_plan: QueryPlan
    generated_sql: GeneratedSql | None = None
    validation: SqlValidationResult | None = None
    execution: SqlExecutionResult | None = None
    answer: dict[str, Any] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)
    tool_trace: list[ToolTraceStep] = Field(default_factory=list)
    planning_metadata: PlanningMetadata = Field(default_factory=PlanningMetadata)

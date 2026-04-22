from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.llm.types import PipelineMode
from backend.app.text_to_sql.models import QueryPlan

PlannerDecision = Literal["propose_plan", "clarify", "reject"]


class LLMPlannerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PlannerDecision
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    query_plan: QueryPlan | None = None


class LLMToolSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMToolOrchestrationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    steps: list[LLMToolSuggestion] = Field(default_factory=list)


class LLMAuditEntry(BaseModel):
    correlation_id: str
    mode: PipelineMode
    provider: str
    model_name: str
    prompt_template: str
    success: bool
    output_valid: bool
    fallback_used: bool
    error_code: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)


class LLMAuditListResponse(BaseModel):
    count: int = Field(ge=0)
    items: list[LLMAuditEntry] = Field(default_factory=list)

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PipelineMode = Literal["deterministic", "local_llm_hybrid", "local_llm_tool_orchestrated"]
PlanOrigin = Literal["deterministic", "local_llm"]


class PlanningMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_mode: PipelineMode = "deterministic"
    applied_mode: PipelineMode = "deterministic"
    plan_origin: PlanOrigin = "deterministic"
    llm_attempted: bool = False
    llm_used: bool = False
    llm_output_valid: bool | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    orchestration_used: bool = False
    orchestration_steps: list[str] = Field(default_factory=list)

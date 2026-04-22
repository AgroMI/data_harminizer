from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import ToolCategory


class ToolFieldSummary(BaseModel):
    name: str
    type_name: str
    required: bool
    description: str | None = None
    default: object | None = None


class ToolDefinitionResponse(BaseModel):
    tool_name: str
    description: str
    category: ToolCategory
    read_only: bool
    input_fields: list[ToolFieldSummary] = Field(default_factory=list)


class ToolsListResponse(BaseModel):
    count: int = Field(ge=0)
    tools: list[ToolDefinitionResponse] = Field(default_factory=list)


class ToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ToolErrorResponse(BaseModel):
    code: str
    message: str
    details: object | None = None


class ToolExecuteResponse(BaseModel):
    tool_name: str
    success: bool
    result: dict[str, object] | None = None
    error: ToolErrorResponse | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

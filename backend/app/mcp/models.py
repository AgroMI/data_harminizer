from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MCPToolCategory = Literal["schema", "planning", "sql", "metadata", "retrieval"]


class MCPToolDefinition(BaseModel):
    tool_name: str
    description: str
    category: MCPToolCategory
    read_only: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class MCPToolsListResponse(BaseModel):
    count: int = Field(ge=0)
    tools: list[MCPToolDefinition] = Field(default_factory=list)


class MCPInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPErrorResponse(BaseModel):
    code: str
    message: str
    details: Any = None


class MCPInvokeResponse(BaseModel):
    correlation_id: str
    tool_name: str
    success: bool
    result: dict[str, Any] | None = None
    error: MCPErrorResponse | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPAuditEntry(BaseModel):
    correlation_id: str
    tool_name: str
    success: bool
    read_only: bool
    duration_ms: int = Field(default=0, ge=0)
    error_code: str | None = None
    sql_fingerprint: str | None = None
    row_count: int | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    response_payload: dict[str, Any] = Field(default_factory=dict)


class MCPAuditListResponse(BaseModel):
    count: int = Field(ge=0)
    items: list[MCPAuditEntry] = Field(default_factory=list)

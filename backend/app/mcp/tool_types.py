from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from backend.app.mcp.models import MCPToolCategory, MCPToolDefinition


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    correlation_id: str


class BaseMCPTool:
    tool_name: str
    description: str
    category: MCPToolCategory
    read_only: bool = True
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def validate_arguments(self, arguments: dict[str, Any]) -> BaseModel:
        return self.input_model.model_validate(arguments)

    def validate_result(self, result: dict[str, Any]) -> dict[str, Any]:
        validated = self.output_model.model_validate(result)
        return validated.model_dump(mode="json")

    def definition(self) -> MCPToolDefinition:
        return MCPToolDefinition(
            tool_name=self.tool_name,
            description=self.description,
            category=self.category,
            read_only=self.read_only,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
        )

    def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> dict[str, Any]:
        raise NotImplementedError

from __future__ import annotations

from backend.app.tools.metadata_tool import MetadataTool
from backend.app.tools.query_tool import QueryTool
from backend.app.tools.retrieval_tool import RetrievalTool
from backend.app.tools.tool_types import BaseTool, ToolDefinition
from backend.app.tools.unit_conversion_tool import UnitConversionTool


class ToolRegistry:
    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools_by_name = {tool.tool_name: tool for tool in tools}

    def list_tools(self) -> list[ToolDefinition]:
        return [
            self._tools_by_name[name].definition()
            for name in sorted(self._tools_by_name)
        ]

    def get_tool(self, tool_name: str) -> BaseTool | None:
        return self._tools_by_name.get(tool_name)


def default_tool_registry() -> ToolRegistry:
    return DEFAULT_TOOL_REGISTRY


DEFAULT_TOOL_REGISTRY = ToolRegistry(
    tools=[
        MetadataTool(),
        QueryTool(),
        RetrievalTool(),
        UnitConversionTool(),
    ]
)

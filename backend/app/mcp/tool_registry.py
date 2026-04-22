from __future__ import annotations

from backend.app.mcp.tool_types import BaseMCPTool
from backend.app.mcp.tools import (
    DescribeSchemaTool,
    ExecuteSqlTool,
    ExplainMetadataTool,
    GenerateSqlTool,
    PlanQueryTool,
    RetrieveEvidenceTool,
    ValidateSqlTool,
)


class MCPToolRegistry:
    def __init__(self, tools: list[BaseMCPTool]) -> None:
        self._tools_by_name = {tool.tool_name: tool for tool in tools}

    def list_tools(self) -> list[BaseMCPTool]:
        return [self._tools_by_name[name] for name in sorted(self._tools_by_name)]

    def get_tool(self, tool_name: str) -> BaseMCPTool | None:
        return self._tools_by_name.get(tool_name)


def default_mcp_registry() -> MCPToolRegistry:
    return DEFAULT_MCP_REGISTRY


DEFAULT_MCP_REGISTRY = MCPToolRegistry(
    tools=[
        DescribeSchemaTool(),
        ExecuteSqlTool(),
        ExplainMetadataTool(),
        GenerateSqlTool(),
        PlanQueryTool(),
        RetrieveEvidenceTool(),
        ValidateSqlTool(),
    ]
)

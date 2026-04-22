from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from backend.app.mcp.audit import generate_correlation_id, log_tool_call
from backend.app.mcp.errors import MCPError
from backend.app.mcp.models import MCPInvokeResponse
from backend.app.mcp.tool_registry import MCPToolRegistry, default_mcp_registry
from backend.app.mcp.tool_types import ToolExecutionContext


class MCPServer:
    def __init__(self, registry: MCPToolRegistry | None = None) -> None:
        self._registry = registry or default_mcp_registry()

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.definition().model_dump(mode="json") for tool in self._registry.list_tools()]

    def invoke_by_name(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_correlation_id = correlation_id or generate_correlation_id()
        started_at = time.perf_counter()
        tool = self._registry.get_tool(tool_name)
        if tool is None:
            response = self._error_response(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                category=None,
                read_only=None,
                code="invalid_tool_name",
                message=f"Unknown MCP tool: {tool_name}.",
                duration_ms=_duration_ms(started_at),
            )
            log_tool_call(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                success=False,
                read_only=True,
                request_payload=arguments,
                response_payload={},
                error_code="invalid_tool_name",
                duration_ms=response["metadata"]["duration_ms"],
            )
            return response

        try:
            validated_arguments = tool.validate_arguments(arguments)
        except ValidationError as exc:
            response = self._error_response(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                category=tool.category,
                read_only=tool.read_only,
                code="invalid_arguments",
                message="MCP tool arguments failed validation.",
                details=exc.errors(),
                duration_ms=_duration_ms(started_at),
            )
            log_tool_call(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                success=False,
                read_only=tool.read_only,
                request_payload=arguments,
                response_payload={},
                error_code="invalid_arguments",
                duration_ms=response["metadata"]["duration_ms"],
            )
            return response

        try:
            raw_result = tool.execute(
                validated_arguments,
                ToolExecutionContext(correlation_id=resolved_correlation_id),
            )
            result = tool.validate_result(raw_result)
        except MCPError as exc:
            response = self._error_response(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                category=tool.category,
                read_only=tool.read_only,
                code=exc.code,
                message=exc.message,
                details=exc.details,
                duration_ms=_duration_ms(started_at),
            )
            log_tool_call(
                correlation_id=resolved_correlation_id,
                tool_name=tool_name,
                success=False,
                read_only=tool.read_only,
                request_payload=arguments,
                response_payload={},
                error_code=exc.code,
                duration_ms=response["metadata"]["duration_ms"],
                sql_text=str(arguments.get("sql")) if "sql" in arguments else None,
            )
            return response

        duration_ms = _duration_ms(started_at)
        response = MCPInvokeResponse(
            correlation_id=resolved_correlation_id,
            tool_name=tool_name,
            success=True,
            result=result,
            error=None,
            metadata={
                "category": tool.category,
                "read_only": tool.read_only,
                "duration_ms": duration_ms,
            },
        ).model_dump(mode="json")
        execution_payload = result.get("execution") if isinstance(result, dict) else None
        log_tool_call(
            correlation_id=resolved_correlation_id,
            tool_name=tool_name,
            success=True,
            read_only=tool.read_only,
            request_payload=arguments,
            response_payload=result if isinstance(result, dict) else {},
            error_code=None,
            duration_ms=duration_ms,
            sql_text=str(arguments.get("sql")) if "sql" in arguments else None,
            row_count=execution_payload.get("row_count") if isinstance(execution_payload, dict) else None,
        )
        return response

    def _error_response(
        self,
        *,
        correlation_id: str,
        tool_name: str,
        category: str | None,
        read_only: bool | None,
        code: str,
        message: str,
        details: Any = None,
        duration_ms: int,
    ) -> dict[str, Any]:
        return MCPInvokeResponse(
            correlation_id=correlation_id,
            tool_name=tool_name,
            success=False,
            result=None,
            error={
                "code": code,
                "message": message,
                "details": details,
            },
            metadata={
                "category": category,
                "read_only": read_only,
                "duration_ms": duration_ms,
            },
        ).model_dump(mode="json")


def default_mcp_server() -> MCPServer:
    return DEFAULT_MCP_SERVER


DEFAULT_MCP_SERVER = MCPServer()


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)

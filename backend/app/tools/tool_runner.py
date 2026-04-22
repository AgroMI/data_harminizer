from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.tools.tool_registry import ToolRegistry, default_tool_registry


def execute_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    registry: ToolRegistry | None = None,
) -> dict[str, object]:
    resolved_registry = registry or default_tool_registry()
    tool = resolved_registry.get_tool(tool_name)
    if tool is None:
        return _error_response(
            tool_name=tool_name,
            category=None,
            read_only=None,
            code="invalid_tool_name",
            message=f"Unknown tool: {tool_name}.",
        )

    try:
        validated_arguments = tool.validate_arguments(arguments)
    except ValidationError as exc:
        return _error_response(
            tool_name=tool_name,
            category=tool.category,
            read_only=tool.read_only,
            code="invalid_arguments",
            message="Tool arguments failed validation.",
            details=exc.errors(),
        )

    try:
        result = tool.execute(validated_arguments)
    except HTTPException as exc:
        return _error_response(
            tool_name=tool_name,
            category=tool.category,
            read_only=tool.read_only,
            code="tool_execution_error",
            message=str(exc.detail),
        )
    except ValueError as exc:
        return _error_response(
            tool_name=tool_name,
            category=tool.category,
            read_only=tool.read_only,
            code="tool_execution_error",
            message=str(exc),
        )

    return {
        "tool_name": tool_name,
        "success": True,
        "result": result,
        "error": None,
        "metadata": {
            "category": tool.category,
            "read_only": tool.read_only,
        },
    }


def _error_response(
    *,
    tool_name: str,
    category: str | None,
    read_only: bool | None,
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "success": False,
        "result": None,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "metadata": {
            "category": category,
            "read_only": read_only,
        },
    }

from __future__ import annotations

from backend.app.tools.tool_registry import default_tool_registry


def test_tool_registry_lists_expected_read_only_tools() -> None:
    registry = default_tool_registry()

    tools = registry.list_tools()
    tool_names = {tool.tool_name for tool in tools}

    assert tool_names == {
        "metadata_tool",
        "query_tool",
        "retrieval_tool",
        "unit_conversion_tool",
    }
    assert all(tool.read_only is True for tool in tools)
    assert {tool.category for tool in tools} == {"metadata", "query", "retrieval", "conversion"}


def test_tool_registry_exposes_input_field_summaries() -> None:
    registry = default_tool_registry()

    query_tool = next(tool for tool in registry.list_tools() if tool.tool_name == "query_tool")
    field_names = {field.name for field in query_tool.input_fields}

    assert {"operation", "filters", "limit", "group_by", "metric", "include_invalid"} <= field_names

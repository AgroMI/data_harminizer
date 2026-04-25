"""
Kísérleti külső MCP-kompatibilis adapter — MVP szint.

Ez a modul a belső MCPServer-t adaptálja a Model Context Protocol (MCP)
JSON-RPC 2.0 interfészéhez. Nem valósít meg teljes MCP platformot,
nem tartalmaz auth/session/permission kezelést, és a meglévő belső
tool registry-re és SQL-validációs rétegre épít.

Referencia: https://modelcontextprotocol.io/specification/2024-11-05
"""
from __future__ import annotations

import json
from typing import Any

from backend.app.mcp.server import default_mcp_server

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "atk-mcp-adapter"
_SERVER_VERSION = "0.1.0-mvp"


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """MCP initialize handshake — returns server capabilities."""
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": _SERVER_NAME,
            "version": _SERVER_VERSION,
        },
    }


def handle_tools_list(params: dict[str, Any]) -> dict[str, Any]:
    """Return available tools in MCP protocol format.

    Delegates to the internal MCPToolRegistry via MCPServer.list_tools().
    Does not duplicate tool definitions — reads them from the registry.
    """
    internal_tools = default_mcp_server().list_tools()
    mcp_tools = [
        {
            "name": t["tool_name"],
            "description": t["description"],
            "inputSchema": t.get("input_schema") or {"type": "object", "properties": {}},
        }
        for t in internal_tools
    ]
    return {"tools": mcp_tools}


def handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """Invoke an internal tool and wrap the result in MCP content format.

    Delegates entirely to MCPServer.invoke_by_name(), which enforces:
    - argument validation via Pydantic,
    - SQL validation through the existing safe-query pipeline,
    - read-only PostgreSQL transaction enforcement,
    - audit logging to ops.mcp_tool_audit_log.
    No direct SQL execution is performed here.
    """
    tool_name: str | None = params.get("name")
    if not tool_name:
        raise ValueError("Missing required param: name")
    arguments: dict[str, Any] = params.get("arguments") or {}

    response = default_mcp_server().invoke_by_name(
        tool_name=tool_name,
        arguments=arguments,
    )

    if not response.get("success"):
        error = response.get("error") or {}
        error_text = (
            f"Tool error [{error.get('code', 'unknown')}]: "
            f"{error.get('message', 'Unknown error')}"
        )
        return {
            "content": [{"type": "text", "text": error_text}],
            "isError": True,
        }

    result = response.get("result") or {}
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }

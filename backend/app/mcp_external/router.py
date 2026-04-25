"""
Kísérleti külső MCP-kompatibilis FastAPI router — MVP szint.

Egyetlen POST /mcp endpointot regisztrál, amely JSON-RPC 2.0 üzeneteket
fogad és a belső MCPServer-re delegál.

Támogatott metódusok:
  - initialize          MCP képességcsere
  - notifications/initialized  Kliens értesítés (nem igényel választ)
  - tools/list          Elérhető toolok listája
  - tools/call          Tool meghívása

Nem támogatott (MVP korlát):
  - Autentikáció, session kezelés, RBAC
  - SSE / streaming transport
  - Teljes MCP specifikáció (resources, prompts, sampling stb.)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.mcp_external.adapter import (
    handle_initialize,
    handle_tools_call,
    handle_tools_list,
)

router = APIRouter(prefix="/mcp", tags=["mcp-external"])

_JSONRPC = "2.0"
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


class _JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str = Field(min_length=1)
    params: dict[str, Any] | list | None = None


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": _JSONRPC, "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": _JSONRPC,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


@router.post(
    "",
    summary="Kísérleti külső MCP-kompatibilis adapter (MVP)",
    description=(
        "JSON-RPC 2.0 alapú MCP-kompatibilis endpoint. "
        "Delegál a meglévő belső MCP tool registry-re. "
        "MVP szint: nincs auth, session vagy teljes MCP specifikáció-lefedettség."
    ),
)
def handle_mcp_request(payload: _JsonRpcRequest) -> dict[str, Any]:
    rid = payload.id
    method = payload.method
    params: dict[str, Any] = (
        payload.params if isinstance(payload.params, dict) else {}
    )

    if method == "initialize":
        return _ok(rid, handle_initialize(params))

    if method == "notifications/initialized":
        return {"jsonrpc": _JSONRPC, "id": rid, "result": {}}

    if method == "tools/list":
        return _ok(rid, handle_tools_list(params))

    if method == "tools/call":
        try:
            result = handle_tools_call(params)
        except ValueError as exc:
            return _rpc_error(rid, _INVALID_PARAMS, str(exc))
        return _ok(rid, result)

    return _rpc_error(rid, _METHOD_NOT_FOUND, f"Method not found: {method}")

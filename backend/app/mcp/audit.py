from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.app.db import get_conn
from backend.app.mcp.models import MCPAuditEntry


def generate_correlation_id() -> str:
    return str(uuid4())


def log_tool_call(
    *,
    correlation_id: str,
    tool_name: str,
    success: bool,
    read_only: bool,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    error_code: str | None,
    duration_ms: int,
    sql_text: str | None = None,
    row_count: int | None = None,
) -> None:
    sql_fingerprint = hashlib.sha256(sql_text.encode("utf-8")).hexdigest() if sql_text else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.mcp_tool_audit_log (
                    correlation_id,
                    tool_name,
                    success,
                    read_only,
                    request_payload,
                    response_payload,
                    error_code,
                    duration_ms,
                    sql_text,
                    sql_fingerprint,
                    row_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    correlation_id,
                    tool_name,
                    success,
                    read_only,
                    Jsonb(request_payload),
                    Jsonb(response_payload),
                    error_code,
                    duration_ms,
                    sql_text,
                    sql_fingerprint,
                    row_count,
                ),
            )
        conn.commit()


def list_audit_entries(*, correlation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = """
    SELECT
        correlation_id,
        tool_name,
        success,
        read_only,
        duration_ms,
        error_code,
        sql_fingerprint,
        row_count,
        request_payload,
        response_payload
    FROM ops.mcp_tool_audit_log
    """
    params: list[object] = []
    if correlation_id:
        sql = f"{sql} WHERE correlation_id = %s"
        params.append(correlation_id)
    sql = f"{sql} ORDER BY id DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchall()


def build_audit_list_response(*, correlation_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    items = [MCPAuditEntry.model_validate(row).model_dump(mode="json") for row in list_audit_entries(correlation_id=correlation_id, limit=limit)]
    return {"count": len(items), "items": items}

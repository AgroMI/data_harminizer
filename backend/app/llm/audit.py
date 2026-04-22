from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from backend.app.db import get_conn
from backend.app.llm.models import LLMAuditEntry


def log_llm_call(
    *,
    correlation_id: str,
    mode: str,
    provider: str,
    model_name: str,
    prompt_template: str,
    success: bool,
    output_valid: bool,
    fallback_used: bool,
    error_code: str | None,
    duration_ms: int,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.llm_planner_audit_log (
                    correlation_id,
                    mode,
                    provider,
                    model_name,
                    prompt_template,
                    success,
                    output_valid,
                    fallback_used,
                    error_code,
                    duration_ms,
                    request_payload,
                    response_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    correlation_id,
                    mode,
                    provider,
                    model_name,
                    prompt_template,
                    success,
                    output_valid,
                    fallback_used,
                    error_code,
                    duration_ms,
                    Jsonb(request_payload),
                    Jsonb(response_payload),
                ),
            )
        conn.commit()


def list_llm_audit_entries(*, correlation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = """
    SELECT
        correlation_id,
        mode,
        provider,
        model_name,
        prompt_template,
        success,
        output_valid,
        fallback_used,
        error_code,
        duration_ms,
        request_payload,
        response_payload
    FROM ops.llm_planner_audit_log
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


def build_llm_audit_list_response(*, correlation_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    items = [
        LLMAuditEntry.model_validate(row).model_dump(mode="json")
        for row in list_llm_audit_entries(correlation_id=correlation_id, limit=limit)
    ]
    return {"count": len(items), "items": items}

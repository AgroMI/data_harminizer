import time
from datetime import date, datetime
from typing import Any

from backend.app.db import get_conn
from backend.app.text_to_sql.catalog import MAX_RECORD_LIMIT, SQL_EXECUTION_TIMEOUT_MS
from backend.app.text_to_sql.models import GeneratedSql, SqlExecutionResult


def execute_generated_sql(
    *,
    sql_bundle: GeneratedSql,
    timeout_ms: int = SQL_EXECUTION_TIMEOUT_MS,
    row_cap: int = MAX_RECORD_LIMIT,
) -> SqlExecutionResult:
    started_at = time.perf_counter()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'")
            cur.execute(sql_bundle.sql, tuple(sql_bundle.parameters))
            rows = cur.fetchall()
            conn.rollback()

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    serialized_rows = [_serialize_row(row) for row in rows[:row_cap]]
    columns = list(serialized_rows[0].keys()) if serialized_rows else list(sql_bundle.projected_columns)
    return SqlExecutionResult(
        columns=columns,
        rows=serialized_rows,
        row_count=len(serialized_rows),
        truncated=len(rows) > row_cap,
        duration_ms=duration_ms,
    )


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _serialize_value(value)
        for key, value in row.items()
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value

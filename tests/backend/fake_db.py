from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from typing import Any


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def _unwrap_json(value: Any) -> Any:
    return deepcopy(getattr(value, "obj", value))


class FakeDatabase:
    def __init__(self) -> None:
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.upload_sessions: dict[str, dict[str, Any]] = {}
        self.staging_rows: list[dict[str, Any]] = []
        self.harmonized_rows: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.llm_audit_logs: list[dict[str, Any]] = []


def _matches_optional_filter(row: dict[str, Any], key: str, value: Any) -> bool:
    if value is None:
        return True
    return row.get(key) == value


def _has_quality_flag(row: dict[str, Any], quality_flag: str | None) -> bool:
    if quality_flag is None:
        return True
    flags = row.get("quality_flags") or []
    return quality_flag in flags


def _matches_date_from(row: dict[str, Any], date_from: date | None) -> bool:
    if date_from is None:
        return True
    value = row.get("observation_date")
    return isinstance(value, date) and value >= date_from


def _matches_date_to(row: dict[str, Any], date_to: date | None) -> bool:
    if date_to is None:
        return True
    value = row.get("observation_date")
    return isinstance(value, date) and value <= date_to


def _apply_harmonized_filters(
    rows: list[dict[str, Any]],
    *,
    upload_id: str | None = None,
    variable: str | None = None,
    variety: str | None = None,
    location: str | None = None,
    treatment: str | None = None,
    plot_id: str | None = None,
    observation_date_from: date | None = None,
    observation_date_to: date | None = None,
    validation_status: str | None = None,
    validation_statuses: list[str] | None = None,
    quality_flag: str | None = None,
    normalized_unit: str | None = None,
) -> list[dict[str, Any]]:
    return [
        deepcopy(row)
        for row in rows
        if _matches_optional_filter(row, "upload_session_id", upload_id)
        and _matches_optional_filter(row, "variable", variable)
        and _matches_optional_filter(row, "variety", variety)
        and _matches_optional_filter(row, "location", location)
        and _matches_optional_filter(row, "treatment", treatment)
        and _matches_optional_filter(row, "plot_id", plot_id)
        and _matches_date_from(row, observation_date_from)
        and _matches_date_to(row, observation_date_to)
        and _matches_optional_filter(row, "validation_status", validation_status)
        and (validation_statuses is None or row.get("validation_status") in validation_statuses)
        and _matches_optional_filter(row, "normalized_unit", normalized_unit)
        and _has_quality_flag(row, quality_flag)
    ]


class FakeCursor:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db
        self._results: list[dict[str, Any]] = []
        self.rowcount = -1

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        normalized = _normalize_sql(sql)
        values = params or ()

        if normalized == "BEGIN READ ONLY":
            self.rowcount = -1
            return

        if normalized.startswith("SET LOCAL statement_timeout ="):
            self.rowcount = -1
            return

        if normalized.startswith("INSERT INTO raw.artifacts"):
            (
                artifact_id,
                filename,
                mime_type,
                file_size_bytes,
                file_hash_sha256,
                uploaded_at,
                parser_version,
                storage_type,
                storage_path,
                raw_content,
                sheet_manifest,
                preview_generated_at,
                parse_warning_summary,
            ) = values
            self.db.artifacts[str(artifact_id)] = {
                "id": str(artifact_id),
                "original_filename": filename,
                "mime_type": mime_type,
                "file_size_bytes": file_size_bytes,
                "file_hash_sha256": file_hash_sha256,
                "uploaded_at": uploaded_at,
                "parser_version": parser_version,
                "storage_type": storage_type,
                "storage_path": storage_path,
                "raw_content": raw_content,
                "sheet_manifest": _unwrap_json(sheet_manifest),
                "preview_generated_at": preview_generated_at,
                "parse_warning_summary": _unwrap_json(parse_warning_summary),
            }
            self.rowcount = 1
            return

        if normalized.startswith("INSERT INTO raw.upload_sessions"):
            upload_id, uploader_user_id, status, filename, artifact_id, preview_json = values
            self.db.upload_sessions[str(upload_id)] = {
                "id": str(upload_id),
                "uploader_user_id": uploader_user_id,
                "status": status,
                "original_filename": filename,
                "artifact_id": str(artifact_id),
                "preview_json": _unwrap_json(preview_json),
            }
            self.rowcount = 1
            return

        if normalized.startswith(
            "SELECT s.id, s.status, s.preview_json, a.id AS artifact_id, a.original_filename, a.mime_type, a.file_size_bytes, a.file_hash_sha256, a.uploaded_at, a.parser_version, a.storage_type, a.storage_path, a.sheet_manifest, a.preview_generated_at, a.parse_warning_summary FROM raw.upload_sessions AS s LEFT JOIN raw.artifacts AS a ON a.id = s.artifact_id WHERE s.id = %s"
        ):
            upload_id = str(values[0])
            session = self.db.upload_sessions.get(upload_id)
            if session is None:
                self._results = []
            else:
                artifact = self.db.artifacts.get(str(session.get("artifact_id")))
                row = {
                    "id": upload_id,
                    "status": session["status"],
                    "preview_json": deepcopy(session["preview_json"]),
                    "artifact_id": artifact["id"] if artifact else None,
                    "original_filename": artifact["original_filename"] if artifact else None,
                    "mime_type": artifact["mime_type"] if artifact else None,
                    "file_size_bytes": artifact["file_size_bytes"] if artifact else None,
                    "file_hash_sha256": artifact["file_hash_sha256"] if artifact else None,
                    "uploaded_at": artifact["uploaded_at"] if artifact else None,
                    "parser_version": artifact["parser_version"] if artifact else None,
                    "storage_type": artifact["storage_type"] if artifact else None,
                    "storage_path": artifact["storage_path"] if artifact else None,
                    "sheet_manifest": deepcopy(artifact["sheet_manifest"]) if artifact else [],
                    "preview_generated_at": artifact["preview_generated_at"] if artifact else None,
                    "parse_warning_summary": deepcopy(artifact["parse_warning_summary"]) if artifact else [],
                }
                self._results = [row]
            self.rowcount = len(self._results)
            return

        if normalized == "SELECT preview_json FROM raw.upload_sessions WHERE id = %s":
            upload_id = str(values[0])
            session = self.db.upload_sessions.get(upload_id)
            self._results = [{"preview_json": deepcopy(session["preview_json"])}] if session else []
            self.rowcount = len(self._results)
            return

        if normalized == "SELECT preview_json FROM raw.upload_sessions WHERE id = %s FOR UPDATE":
            upload_id = str(values[0])
            session = self.db.upload_sessions.get(upload_id)
            self._results = [{"preview_json": deepcopy(session["preview_json"])}] if session else []
            self.rowcount = len(self._results)
            return

        if normalized.startswith("UPDATE raw.upload_sessions SET preview_json = %s, updated_at = now() WHERE id = %s"):
            preview_json, upload_id = values
            self.db.upload_sessions[str(upload_id)]["preview_json"] = _unwrap_json(preview_json)
            self.rowcount = 1
            return

        if normalized == "DELETE FROM harmonized.observations WHERE upload_session_id = %s":
            upload_id = str(values[0])
            before = len(self.db.harmonized_rows)
            self.db.harmonized_rows = [
                row for row in self.db.harmonized_rows if row["upload_session_id"] != upload_id
            ]
            self.rowcount = before - len(self.db.harmonized_rows)
            return

        if normalized == "DELETE FROM staging.observations WHERE upload_session_id = %s":
            upload_id = str(values[0])
            before = len(self.db.staging_rows)
            self.db.staging_rows = [row for row in self.db.staging_rows if row["upload_session_id"] != upload_id]
            self.rowcount = before - len(self.db.staging_rows)
            return

        if normalized.startswith("INSERT INTO harmonized.observations"):
            upload_id = str(values[0])
            inserted = [
                deepcopy(row)
                for row in self.db.staging_rows
                if row["upload_session_id"] == upload_id
                and row["variable"] is not None
                and str(row["variable"]).strip()
            ]
            self.db.harmonized_rows.extend(inserted)
            self.rowcount = len(inserted)
            return

        if normalized.startswith("UPDATE raw.upload_sessions SET status = %s, updated_at = now() WHERE id = %s"):
            status, upload_id = values
            self.db.upload_sessions[str(upload_id)]["status"] = status
            self.rowcount = 1
            return

        if normalized.startswith("UPDATE raw.upload_sessions SET status = %s, preview_json = %s, updated_at = now() WHERE id = %s"):
            status, preview_json, upload_id = values
            session = self.db.upload_sessions[str(upload_id)]
            session["status"] = status
            session["preview_json"] = _unwrap_json(preview_json)
            self.rowcount = 1
            return

        if normalized.startswith("SELECT upload_session_id::text AS upload_session_id, observation_date"):
            params_iter = iter(values)
            upload_id = str(next(params_iter)) if "upload_session_id = %s" in normalized else None
            variable = next(params_iter) if "variable = %s" in normalized else None
            variety = next(params_iter) if "variety = %s" in normalized else None
            location = next(params_iter) if "location = %s" in normalized else None
            treatment = next(params_iter) if "treatment = %s" in normalized else None
            plot_id = next(params_iter) if "plot_id = %s" in normalized else None
            observation_date_from = next(params_iter) if "observation_date >= %s" in normalized else None
            observation_date_to = next(params_iter) if "observation_date <= %s" in normalized else None
            validation_status = next(params_iter) if "validation_status = %s" in normalized else None
            quality_flag = None
            if "quality_flags @> %s" in normalized:
                quality_flag_payload = _unwrap_json(next(params_iter))
                if isinstance(quality_flag_payload, list) and quality_flag_payload:
                    quality_flag = str(quality_flag_payload[0])
            normalized_unit = next(params_iter) if "normalized_unit = %s" in normalized else None
            limit = int(next(params_iter))

            rows = _apply_harmonized_filters(
                self.db.harmonized_rows,
                upload_id=upload_id,
                variable=variable,
                variety=variety,
                location=location,
                treatment=treatment,
                plot_id=plot_id,
                observation_date_from=observation_date_from,
                observation_date_to=observation_date_to,
                validation_status=validation_status,
                quality_flag=quality_flag,
                normalized_unit=normalized_unit,
            )
            rows.sort(
                key=lambda item: (
                    item["observation_date"] is None,
                    item["observation_date"] or date.max,
                    item["variable"] or "",
                    item["plot_id"] is None,
                    item["plot_id"] or "",
                    item["source_sheet"],
                    item["block_id"],
                    item["source_row_index"],
                    item["source_column"],
                )
            )
            self._results = rows[:limit]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT variable FROM harmonized.observations WHERE variable IS NOT NULL ORDER BY variable"):
            values_list = sorted({row["variable"] for row in self.db.harmonized_rows if row.get("variable") is not None})
            self._results = [{"variable": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT normalized_unit FROM harmonized.observations WHERE normalized_unit IS NOT NULL ORDER BY normalized_unit"):
            values_list = sorted({row["normalized_unit"] for row in self.db.harmonized_rows if row.get("normalized_unit") is not None})
            self._results = [{"normalized_unit": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT variety FROM harmonized.observations WHERE variety IS NOT NULL ORDER BY variety"):
            values_list = sorted({row["variety"] for row in self.db.harmonized_rows if row.get("variety") is not None})
            self._results = [{"variety": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT location FROM harmonized.observations WHERE location IS NOT NULL ORDER BY location"):
            values_list = sorted({row["location"] for row in self.db.harmonized_rows if row.get("location") is not None})
            self._results = [{"location": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT treatment FROM harmonized.observations WHERE treatment IS NOT NULL ORDER BY treatment"):
            values_list = sorted({row["treatment"] for row in self.db.harmonized_rows if row.get("treatment") is not None})
            self._results = [{"treatment": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT plot_id FROM harmonized.observations WHERE plot_id IS NOT NULL ORDER BY plot_id"):
            values_list = sorted({row["plot_id"] for row in self.db.harmonized_rows if row.get("plot_id") is not None})
            self._results = [{"plot_id": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT validation_status FROM harmonized.observations WHERE validation_status IS NOT NULL ORDER BY validation_status"):
            values_list = sorted({row["validation_status"] for row in self.db.harmonized_rows if row.get("validation_status") is not None})
            self._results = [{"validation_status": value} for value in values_list]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT DISTINCT jsonb_array_elements_text(quality_flags) AS quality_flag FROM harmonized.observations WHERE quality_flags <> '[]'::jsonb ORDER BY quality_flag"):
            flag_values = sorted(
                {
                    str(flag)
                    for row in self.db.harmonized_rows
                    for flag in row.get("quality_flags", [])
                    if row.get("quality_flags")
                }
            )
            self._results = [{"quality_flag": value} for value in flag_values]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT variety AS group_value, avg(normalized_value)::double precision AS metric_value, count(*)::integer AS record_count, max(normalized_unit) AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="variety", metric="avg_normalized_value")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT treatment AS group_value, avg(normalized_value)::double precision AS metric_value, count(*)::integer AS record_count, max(normalized_unit) AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="treatment", metric="avg_normalized_value")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT location AS group_value, avg(normalized_value)::double precision AS metric_value, count(*)::integer AS record_count, max(normalized_unit) AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="location", metric="avg_normalized_value")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT variety AS group_value, count(*)::integer AS metric_value, count(*)::integer AS record_count, NULL::text AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="variety", metric="count")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT treatment AS group_value, count(*)::integer AS metric_value, count(*)::integer AS record_count, NULL::text AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="treatment", metric="count")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT location AS group_value, count(*)::integer AS metric_value, count(*)::integer AS record_count, NULL::text AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="location", metric="count")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT validation_status AS group_value, count(*)::integer AS metric_value, count(*)::integer AS record_count, NULL::text AS normalized_unit FROM harmonized.observations"):
            self._results = _aggregate_rows(self.db.harmonized_rows, normalized, values, group_key="validation_status", metric="count")
            self.rowcount = len(self._results)
            return

        if normalized.startswith("INSERT INTO ops.mcp_tool_audit_log"):
            (
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
                row_count,
            ) = values
            self.db.audit_logs.append(
                {
                    "correlation_id": str(correlation_id),
                    "tool_name": str(tool_name),
                    "success": bool(success),
                    "read_only": bool(read_only),
                    "request_payload": _unwrap_json(request_payload),
                    "response_payload": _unwrap_json(response_payload),
                    "error_code": error_code,
                    "duration_ms": int(duration_ms),
                    "sql_fingerprint": sql_fingerprint,
                    "row_count": row_count,
                }
            )
            self.rowcount = 1
            return

        if normalized.startswith("INSERT INTO ops.llm_planner_audit_log"):
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
                request_payload,
                response_payload,
            ) = values
            self.db.llm_audit_logs.append(
                {
                    "correlation_id": str(correlation_id),
                    "mode": str(mode),
                    "provider": str(provider),
                    "model_name": str(model_name),
                    "prompt_template": str(prompt_template),
                    "success": bool(success),
                    "output_valid": bool(output_valid),
                    "fallback_used": bool(fallback_used),
                    "error_code": error_code,
                    "duration_ms": int(duration_ms),
                    "request_payload": _unwrap_json(request_payload),
                    "response_payload": _unwrap_json(response_payload),
                }
            )
            self.rowcount = 1
            return

        if normalized.startswith("SELECT correlation_id, tool_name, success, read_only, duration_ms, error_code, sql_fingerprint, row_count, request_payload, response_payload FROM ops.mcp_tool_audit_log"):
            results = list(reversed(self.db.audit_logs))
            if "WHERE correlation_id = %s" in normalized:
                correlation_id = str(values[0])
                limit = int(values[1])
                results = [item for item in results if item["correlation_id"] == correlation_id]
            else:
                limit = int(values[0])
            self._results = [deepcopy(item) for item in results[:limit]]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT correlation_id, mode, provider, model_name, prompt_template, success, output_valid, fallback_used, error_code, duration_ms, request_payload, response_payload FROM ops.llm_planner_audit_log"):
            results = list(reversed(self.db.llm_audit_logs))
            if "WHERE correlation_id = %s" in normalized:
                correlation_id = str(values[0])
                limit = int(values[1])
                results = [item for item in results if item["correlation_id"] == correlation_id]
            else:
                limit = int(values[0])
            self._results = [deepcopy(item) for item in results[:limit]]
            self.rowcount = len(self._results)
            return

        if normalized.startswith("SELECT upload_session_id, observation_date, plot_id, variety, treatment, location, variable, value, unit, normalized_value, normalized_unit, validation_status, quality_flags FROM safe.harmonized_observations_v1"):
            rows = _select_safe_rows(self.db.harmonized_rows, normalized, values)
            self._results = rows
            self.rowcount = len(rows)
            return

        if normalized.startswith("SELECT") and "FROM safe.harmonized_observations_v1" in normalized and "metric_value" in normalized:
            rows = _aggregate_safe_sql(self.db.harmonized_rows, normalized, values)
            self._results = rows
            self.rowcount = len(rows)
            return

        raise NotImplementedError(f"Unhandled SQL in fake database: {normalized}")

    def executemany(self, sql: str, params_seq: list[tuple[Any, ...]]) -> None:
        normalized = _normalize_sql(sql)
        if not normalized.startswith("INSERT INTO staging.observations"):
            raise NotImplementedError(f"Unhandled executemany SQL in fake database: {normalized}")

        for params in params_seq:
            (
                upload_session_id,
                block_id,
                source_sheet,
                source_row_index,
                source_column,
                observation_date,
                plot_id,
                variety,
                treatment,
                location,
                variable,
                value,
                unit,
                normalized_value,
                normalized_unit,
                validation_status,
                quality_flags,
                dimensions_json,
            ) = params
            self.db.staging_rows.append(
                {
                    "upload_session_id": str(upload_session_id),
                    "block_id": block_id,
                    "source_sheet": source_sheet,
                    "source_row_index": source_row_index,
                    "source_column": source_column,
                    "observation_date": observation_date,
                    "plot_id": plot_id,
                    "variety": variety,
                    "treatment": treatment,
                    "location": location,
                    "variable": variable,
                    "value": value,
                    "unit": unit,
                    "normalized_value": normalized_value,
                    "normalized_unit": normalized_unit,
                    "validation_status": validation_status,
                    "quality_flags": _unwrap_json(quality_flags),
                    "dimensions_json": _unwrap_json(dimensions_json),
                }
            )

        self.rowcount = len(params_seq)

    def fetchone(self) -> dict[str, Any] | None:
        if not self._results:
            return None
        return self._results[0]

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._results)


class FakeConnection:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.db)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


@contextmanager
def fake_get_conn(db: FakeDatabase):
    yield FakeConnection(db)


def _aggregate_rows(
    rows: list[dict[str, Any]],
    normalized_sql: str,
    values: tuple[Any, ...],
    *,
    group_key: str,
    metric: str,
) -> list[dict[str, Any]]:
    params_iter = iter(values)
    upload_id = str(next(params_iter)) if "upload_session_id = %s" in normalized_sql else None
    variable = next(params_iter) if "variable = %s" in normalized_sql else None
    variety = next(params_iter) if "variety = %s" in normalized_sql else None
    location = next(params_iter) if "location = %s" in normalized_sql else None
    treatment = next(params_iter) if "treatment = %s" in normalized_sql else None
    plot_id = next(params_iter) if "plot_id = %s" in normalized_sql else None
    observation_date_from = next(params_iter) if "observation_date >= %s" in normalized_sql else None
    observation_date_to = next(params_iter) if "observation_date <= %s" in normalized_sql else None
    validation_status = next(params_iter) if "validation_status = %s" in normalized_sql else None
    quality_flag = None
    if "quality_flags @> %s" in normalized_sql:
        quality_flag_payload = _unwrap_json(next(params_iter))
        if isinstance(quality_flag_payload, list) and quality_flag_payload:
            quality_flag = str(quality_flag_payload[0])
    normalized_unit = next(params_iter) if "normalized_unit = %s" in normalized_sql else None

    filtered_rows = _apply_harmonized_filters(
        rows,
        upload_id=upload_id,
        variable=variable,
        variety=variety,
        location=location,
        treatment=treatment,
        plot_id=plot_id,
        observation_date_from=observation_date_from,
        observation_date_to=observation_date_to,
        validation_status=validation_status,
        quality_flag=quality_flag,
        normalized_unit=normalized_unit,
    )

    if "normalized_value IS NOT NULL" in normalized_sql:
        filtered_rows = [row for row in filtered_rows if row.get("normalized_value") is not None]
    if "validation_status <> 'invalid'" in normalized_sql:
        filtered_rows = [row for row in filtered_rows if row.get("validation_status") != "invalid"]

    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for row in filtered_rows:
        grouped.setdefault(row.get(group_key), []).append(row)

    aggregated_rows: list[dict[str, Any]] = []
    for group_value, group_rows in grouped.items():
        record_count = len(group_rows)
        if metric == "avg_normalized_value":
            numeric_values = [float(row["normalized_value"]) for row in group_rows if row.get("normalized_value") is not None]
            metric_value: float | int = sum(numeric_values) / len(numeric_values) if numeric_values else 0.0
            output_unit = next((row.get("normalized_unit") for row in group_rows if row.get("normalized_unit")), None)
        else:
            metric_value = record_count
            output_unit = None

        aggregated_rows.append(
            {
                "group_value": group_value,
                "metric_value": metric_value,
                "record_count": record_count,
                "normalized_unit": output_unit,
            }
        )

    aggregated_rows.sort(key=lambda item: (item["group_value"] is None, item["group_value"] or ""))
    return aggregated_rows


def _select_safe_rows(
    rows: list[dict[str, Any]],
    normalized_sql: str,
    values: tuple[Any, ...],
) -> list[dict[str, Any]]:
    filters, limit = _parse_safe_filters_and_limit(normalized_sql, values)
    selected_rows = _apply_harmonized_filters(rows, **filters)
    selected_rows.sort(
        key=lambda item: (
            item.get("observation_date") is None,
            item.get("observation_date") or date.max,
            item.get("variable") or "",
            item.get("plot_id") is None,
            item.get("plot_id") or "",
        )
    )
    return [
        {
            "upload_session_id": row.get("upload_session_id"),
            "observation_date": row.get("observation_date"),
            "plot_id": row.get("plot_id"),
            "variety": row.get("variety"),
            "treatment": row.get("treatment"),
            "location": row.get("location"),
            "variable": row.get("variable"),
            "value": row.get("value"),
            "unit": row.get("unit"),
            "normalized_value": row.get("normalized_value"),
            "normalized_unit": row.get("normalized_unit"),
            "validation_status": row.get("validation_status"),
            "quality_flags": list(row.get("quality_flags") or []),
        }
        for row in selected_rows[:limit]
    ]


def _aggregate_safe_sql(
    rows: list[dict[str, Any]],
    normalized_sql: str,
    values: tuple[Any, ...],
) -> list[dict[str, Any]]:
    filters, limit = _parse_safe_filters_and_limit(normalized_sql, values)
    filtered_rows = _apply_harmonized_filters(rows, **filters)
    if "normalized_value IS NOT NULL" in normalized_sql:
        filtered_rows = [row for row in filtered_rows if row.get("normalized_value") is not None]
    if "validation_status <> 'invalid'" in normalized_sql:
        filtered_rows = [row for row in filtered_rows if row.get("validation_status") != "invalid"]

    group_key = None
    if "GROUP BY variety" in normalized_sql:
        group_key = "variety"
    elif "GROUP BY treatment" in normalized_sql:
        group_key = "treatment"
    elif "GROUP BY location" in normalized_sql:
        group_key = "location"
    elif "GROUP BY validation_status" in normalized_sql:
        group_key = "validation_status"
    elif "GROUP BY plot_id" in normalized_sql:
        group_key = "plot_id"

    metric = "avg" if "avg(normalized_value)" in normalized_sql else "count"
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    if group_key is None:
        grouped[None] = filtered_rows
    else:
        for row in filtered_rows:
            grouped.setdefault(row.get(group_key), []).append(row)

    aggregated_rows: list[dict[str, Any]] = []
    for group_value, group_rows in grouped.items():
        record_count = len(group_rows)
        if metric == "avg":
            numeric_values = [float(row["normalized_value"]) for row in group_rows if row.get("normalized_value") is not None]
            metric_value: float | int = sum(numeric_values) / len(numeric_values) if numeric_values else 0.0
            normalized_unit = next((row.get("normalized_unit") for row in group_rows if row.get("normalized_unit")), None)
        else:
            metric_value = record_count
            normalized_unit = None
        aggregated_rows.append(
            {
                "group_value": group_value,
                "metric_value": metric_value,
                "record_count": record_count,
                "normalized_unit": normalized_unit,
            }
        )

    if "ORDER BY metric_value DESC" in normalized_sql:
        aggregated_rows.sort(key=lambda item: (-float(item["metric_value"]), item.get("group_value") or ""))
    elif "ORDER BY metric_value ASC" in normalized_sql:
        aggregated_rows.sort(key=lambda item: (float(item["metric_value"]), item.get("group_value") or ""))
    else:
        aggregated_rows.sort(key=lambda item: (item.get("group_value") is None, item.get("group_value") or ""))

    return aggregated_rows[:limit]


def _parse_safe_filters_and_limit(
    normalized_sql: str,
    values: tuple[Any, ...],
) -> tuple[dict[str, Any], int]:
    params_iter = iter(values)
    filters: dict[str, Any] = {
        "variety": next(params_iter) if "variety = %s" in normalized_sql else None,
        "location": next(params_iter) if "location = %s" in normalized_sql else None,
        "treatment": next(params_iter) if "treatment = %s" in normalized_sql else None,
        "plot_id": next(params_iter) if "plot_id = %s" in normalized_sql else None,
        "observation_date_from": next(params_iter) if "observation_date >= %s" in normalized_sql else None,
        "observation_date_to": next(params_iter) if "observation_date <= %s" in normalized_sql else None,
        "upload_id": str(next(params_iter)) if "upload_session_id = %s" in normalized_sql else None,
        "validation_status": None,
        "validation_statuses": None,
        "quality_flag": None,
        "variable": None,
        "normalized_unit": None,
    }
    if "validation_status IN (" in normalized_sql:
        placeholder_block = normalized_sql.split("validation_status IN (", 1)[1].split(")", 1)[0]
        placeholder_count = placeholder_block.count("%s")
        filters["validation_statuses"] = [str(next(params_iter)) for _ in range(placeholder_count)]
    elif "validation_status = %s" in normalized_sql:
        filters["validation_status"] = next(params_iter)

    if "variable = %s" in normalized_sql:
        filters["variable"] = next(params_iter)
    if "normalized_unit = %s" in normalized_sql:
        filters["normalized_unit"] = next(params_iter)

    limit = int(next(params_iter))
    return filters, limit

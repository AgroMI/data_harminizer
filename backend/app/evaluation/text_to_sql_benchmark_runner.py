from __future__ import annotations

from collections import defaultdict
from datetime import date as DateValue
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.app.evaluation.text_to_sql_benchmark_dataset import (
    DEFAULT_TEXT_TO_SQL_BENCHMARK_DATASET_PATH,
    load_text_to_sql_benchmark_dataset,
    load_text_to_sql_seed_rows,
)
from backend.app.evaluation.text_to_sql_benchmark_scoring import build_report, evaluate_question
from backend.app.evaluation.text_to_sql_benchmark_types import TextToSqlBenchmarkReport
from backend.app.mcp.server import MCPServer
from backend.app.mcp.tools import core_tools
from backend.app.text_to_sql.models import GeneratedSql, SqlExecutionResult
from backend.app.text_to_sql.planner import plan_question
from backend.app.text_to_sql.service import run_text_to_sql_pipeline


class InMemoryBenchmarkBackend:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [dict(row) for row in rows]

    def get_harmonized_query_metadata(self) -> dict[str, Any]:
        return {
            "supported_filters": [
                "upload_session_id",
                "variable",
                "variety",
                "location",
                "treatment",
                "plot_id",
                "observation_date_from",
                "observation_date_to",
                "validation_status",
                "normalized_unit",
            ],
            "supported_group_bys": ["plot_id", "variety", "treatment", "location", "validation_status"],
            "supported_metrics": ["avg_normalized_value", "count"],
            "supported_validation_statuses": ["valid", "warning", "invalid"],
            "supported_quality_flags": [
                "missing_required_dimension",
                "missing_observation_date",
                "missing_unit",
                "missing_measure_value",
                "duplicate_candidate",
                "outlier_candidate",
            ],
            "available_variables": self._distinct_values("variable"),
            "available_normalized_units": self._distinct_values("normalized_unit"),
            "available_varieties": self._distinct_values("variety"),
            "available_locations": self._distinct_values("location"),
            "available_treatments": self._distinct_values("treatment"),
            "available_plot_ids": self._distinct_values("plot_id"),
            "available_validation_statuses": self._distinct_values("validation_status"),
            "available_quality_flags": self._distinct_quality_flags(),
            "aggregations_exclude_invalid_by_default": True,
        }

    def execute_generated_sql(self, *, sql_bundle: GeneratedSql) -> SqlExecutionResult:
        plan, _ = plan_question(question="placeholder", metadata=self.get_harmonized_query_metadata())
        del plan
        sql = sql_bundle.sql
        params = list(sql_bundle.parameters)
        rows = self._execute_sql(sql=sql, params=params)
        return SqlExecutionResult(
            columns=list(rows[0].keys()) if rows else list(sql_bundle.projected_columns),
            rows=rows,
            row_count=len(rows),
            truncated=False,
            duration_ms=0,
        )

    def _execute_sql(self, *, sql: str, params: list[object]) -> list[dict[str, Any]]:
        normalized = " ".join(sql.split())
        filters, limit = self._parse_filters(normalized, params)
        rows = self._apply_filters(filters)
        if normalized.startswith("SELECT upload_session_id"):
            rows.sort(key=lambda item: (item.get("observation_date") or "", item.get("variable") or "", item.get("plot_id") or ""))
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
                for row in rows[:limit]
            ]

        if "normalized_value IS NOT NULL" in normalized:
            rows = [row for row in rows if row.get("normalized_value") is not None]
        if "validation_status <> 'invalid'" in normalized:
            rows = [row for row in rows if row.get("validation_status") != "invalid"]

        group_key = None
        for candidate in ("plot_id", "variety", "treatment", "location", "validation_status"):
            if f"GROUP BY {candidate}" in normalized:
                group_key = candidate
                break

        grouped: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        if group_key is None:
            grouped[None] = rows
        else:
            for row in rows:
                grouped[row.get(group_key)].append(row)

        metric_is_avg = "avg(normalized_value)" in normalized
        items: list[dict[str, Any]] = []
        for group_value, group_rows in grouped.items():
            record_count = len(group_rows)
            if metric_is_avg:
                values = [float(row["normalized_value"]) for row in group_rows if row.get("normalized_value") is not None]
                metric_value: float | int = sum(values) / len(values) if values else 0.0
                normalized_unit = next((row.get("normalized_unit") for row in group_rows if row.get("normalized_unit")), None)
            else:
                metric_value = record_count
                normalized_unit = None
            items.append(
                {
                    "group_value": group_value,
                    "metric_value": metric_value,
                    "record_count": record_count,
                    "normalized_unit": normalized_unit,
                }
            )

        if "ORDER BY metric_value DESC" in normalized:
            items.sort(key=lambda item: (-float(item["metric_value"]), item.get("group_value") or ""))
        elif "ORDER BY metric_value ASC" in normalized:
            items.sort(key=lambda item: (float(item["metric_value"]), item.get("group_value") or ""))
        else:
            items.sort(key=lambda item: (item.get("group_value") is None, item.get("group_value") or ""))
        return items[:limit]

    def _apply_filters(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for row in self._rows:
            if filters["variety"] and row.get("variety") != filters["variety"]:
                continue
            if filters["location"] and row.get("location") != filters["location"]:
                continue
            if filters["treatment"] and row.get("treatment") != filters["treatment"]:
                continue
            if filters["plot_id"] and row.get("plot_id") != filters["plot_id"]:
                continue
            if filters["upload_session_id"] and row.get("upload_session_id") != filters["upload_session_id"]:
                continue
            if filters["validation_status"] and row.get("validation_status") != filters["validation_status"]:
                continue
            if filters["validation_statuses"] and row.get("validation_status") not in filters["validation_statuses"]:
                continue
            if filters["variable"] and row.get("variable") != filters["variable"]:
                continue
            if filters["normalized_unit"] and row.get("normalized_unit") != filters["normalized_unit"]:
                continue
            if filters["date_from"] and self._parse_date(row.get("observation_date")) < filters["date_from"]:
                continue
            if filters["date_to"] and self._parse_date(row.get("observation_date")) > filters["date_to"]:
                continue
            results.append(dict(row))
        return results

    def _parse_filters(self, normalized_sql: str, params: list[object]) -> tuple[dict[str, Any], int]:
        params_iter = iter(params)
        filters = {
            "variety": next(params_iter) if "variety = %s" in normalized_sql else None,
            "location": next(params_iter) if "location = %s" in normalized_sql else None,
            "treatment": next(params_iter) if "treatment = %s" in normalized_sql else None,
            "plot_id": next(params_iter) if "plot_id = %s" in normalized_sql else None,
            "date_from": self._parse_date(next(params_iter)) if "observation_date >= %s" in normalized_sql else None,
            "date_to": self._parse_date(next(params_iter)) if "observation_date <= %s" in normalized_sql else None,
            "upload_session_id": str(next(params_iter)) if "upload_session_id = %s" in normalized_sql else None,
            "validation_status": None,
            "validation_statuses": None,
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

    def _distinct_values(self, field_name: str) -> list[str]:
        return sorted({str(item[field_name]) for item in self._rows if item.get(field_name) is not None})

    def _distinct_quality_flags(self) -> list[str]:
        return sorted({str(flag) for row in self._rows for flag in row.get("quality_flags", []) if flag is not None})

    @staticmethod
    def _parse_date(value: Any) -> DateValue:
        if isinstance(value, DateValue):
            return value
        if isinstance(value, str):
            return DateValue.fromisoformat(value)
        raise ValueError("Benchmark seed row contains invalid observation_date value.")


def run_text_to_sql_benchmark(
    *,
    dataset_path: Path | None = None,
    seed_rows_path: Path | None = None,
) -> TextToSqlBenchmarkReport:
    dataset = load_text_to_sql_benchmark_dataset(dataset_path)
    seed_rows = load_text_to_sql_seed_rows(seed_rows_path)
    backend = InMemoryBenchmarkBackend(seed_rows)
    results = []

    with patch("backend.app.mcp.server.log_tool_call", lambda **_: None):
        with patch("backend.app.text_to_sql.planner.get_harmonized_query_metadata", backend.get_harmonized_query_metadata):
            with patch("backend.app.mcp.tools.core_tools.get_harmonized_query_metadata", backend.get_harmonized_query_metadata):
                with patch("backend.app.mcp.tools.core_tools.execute_generated_sql", backend.execute_generated_sql):
                    server = MCPServer()
                    for question in dataset:
                        response = run_text_to_sql_pipeline(
                            question=question.question,
                            server=server,
                        ).model_dump(mode="json")
                        results.append(evaluate_question(question=question, actual_response=response))

    resolved_dataset_name = "text_to_sql_golden_v1"
    if dataset_path is not None and dataset_path != DEFAULT_TEXT_TO_SQL_BENCHMARK_DATASET_PATH:
        resolved_dataset_name = dataset_path.stem
    return build_report(dataset_name=resolved_dataset_name, results=results, questions=dataset)


def build_text_summary(report: TextToSqlBenchmarkReport) -> str:
    return "\n".join(
        [
            f"Dataset: {report.dataset_name}",
            f"Questions: {report.total_questions}",
            _metric_line("Query plan correctness", report.query_plan_correctness),
            _metric_line("SQL validity rate", report.sql_validity_rate),
            _metric_line("Execution success rate", report.execution_success_rate),
            _metric_line("Answer correctness", report.answer_correctness),
            _metric_line("Unsupported query rate", report.unsupported_query_rate),
            _metric_line("Rejected unsafe query rate", report.rejected_unsafe_query_rate),
        ]
    )


def build_markdown_summary(report: TextToSqlBenchmarkReport) -> str:
    return "\n".join(
        [
            "# Text-to-SQL Benchmark Summary",
            "",
            f"- Dataset: `{report.dataset_name}`",
            f"- Questions: `{report.total_questions}`",
            f"- Query plan correctness: `{report.query_plan_correctness.correct}/{report.query_plan_correctness.total}` ({report.query_plan_correctness.accuracy:.4f})",
            f"- SQL validity rate: `{report.sql_validity_rate.correct}/{report.sql_validity_rate.total}` ({report.sql_validity_rate.accuracy:.4f})",
            f"- Execution success rate: `{report.execution_success_rate.correct}/{report.execution_success_rate.total}` ({report.execution_success_rate.accuracy:.4f})",
            f"- Answer correctness: `{report.answer_correctness.correct}/{report.answer_correctness.total}` ({report.answer_correctness.accuracy:.4f})",
            f"- Unsupported query rate: `{report.unsupported_query_rate.correct}/{report.unsupported_query_rate.total}` ({report.unsupported_query_rate.accuracy:.4f})",
            f"- Rejected unsafe query rate: `{report.rejected_unsafe_query_rate.correct}/{report.rejected_unsafe_query_rate.total}` ({report.rejected_unsafe_query_rate.accuracy:.4f})",
        ]
    )


def _metric_line(label: str, metric: Any) -> str:
    return f"{label}: {metric.correct}/{metric.total} ({metric.accuracy:.4f})"

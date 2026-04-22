from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import date as DateValue
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.evaluation.benchmark_dataset import (
    DEFAULT_BENCHMARK_DATASET_PATH,
    load_benchmark_dataset,
    load_benchmark_seed_rows,
)
from backend.app.evaluation.benchmark_scoring import (
    build_benchmark_report,
    evaluate_benchmark_question,
)
from backend.app.evaluation.benchmark_types import (
    BenchmarkQuestion,
    BenchmarkRunReport,
)
from backend.app.services import nl_query_service

DEFAULT_DATASET_NAME = "nl_query_mvp_golden_v1"


class InMemoryHarmonizedQueryBackend:
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
                "quality_flag",
                "normalized_unit",
            ],
            "supported_group_bys": ["variety", "treatment", "location", "validation_status"],
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

    def list_harmonized_observations(
        self,
        *,
        limit: int,
        filters: Any,
    ) -> dict[str, Any]:
        rows = self._apply_filters(filters=filters)
        rows.sort(key=self._observation_sort_key)
        return {
            "items": rows[:limit],
            "count": min(len(rows), limit),
        }

    def aggregate_harmonized_observations(
        self,
        *,
        group_by: str,
        metric: str,
        filters: Any,
        include_invalid: bool,
    ) -> dict[str, Any]:
        if metric == "avg_normalized_value" and group_by == "validation_status":
            raise HTTPException(
                status_code=422,
                detail="avg_normalized_value is only supported for group_by variety, treatment or location.",
            )

        rows = self._apply_filters(filters=filters)
        if metric == "avg_normalized_value":
            if getattr(filters, "variable", None) is None:
                raise HTTPException(
                    status_code=422,
                    detail="variable is required for avg_normalized_value aggregations.",
                )
            rows = [row for row in rows if row.get("normalized_value") is not None]

        if getattr(filters, "validation_status", None) is None and not include_invalid and group_by != "validation_status":
            rows = [row for row in rows if row.get("validation_status") != "invalid"]

        grouped_rows: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped_rows[self._optional_group_value(row.get(group_by))].append(row)

        items: list[dict[str, Any]] = []
        for group_value, group_items in grouped_rows.items():
            record_count = len(group_items)
            if metric == "avg_normalized_value":
                normalized_values = [float(item["normalized_value"]) for item in group_items]
                metric_value: float | int = sum(normalized_values) / len(normalized_values)
                normalized_unit = next(
                    (item.get("normalized_unit") for item in group_items if item.get("normalized_unit")),
                    None,
                )
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

        items.sort(key=lambda item: (item.get("group_value") is None, item.get("group_value") or ""))
        return {
            "group_by": group_by,
            "metric": metric,
            "include_invalid": include_invalid,
            "items": items,
            "count": len(items),
        }

    def _apply_filters(self, *, filters: Any) -> list[dict[str, Any]]:
        upload_session_id = getattr(filters, "upload_session_id", None)
        variable = getattr(filters, "variable", None)
        variety = getattr(filters, "variety", None)
        location = getattr(filters, "location", None)
        treatment = getattr(filters, "treatment", None)
        plot_id = getattr(filters, "plot_id", None)
        observation_date_from = getattr(filters, "observation_date_from", None)
        observation_date_to = getattr(filters, "observation_date_to", None)
        validation_status = getattr(filters, "validation_status", None)
        quality_flag = getattr(filters, "quality_flag", None)
        normalized_unit = getattr(filters, "normalized_unit", None)

        items: list[dict[str, Any]] = []
        for row in self._rows:
            if upload_session_id and row.get("upload_session_id") != upload_session_id:
                continue
            if variable and row.get("variable") != variable:
                continue
            if variety and row.get("variety") != variety:
                continue
            if location and row.get("location") != location:
                continue
            if treatment and row.get("treatment") != treatment:
                continue
            if plot_id and row.get("plot_id") != plot_id:
                continue
            if normalized_unit and row.get("normalized_unit") != normalized_unit:
                continue
            if validation_status and row.get("validation_status") != validation_status:
                continue
            if quality_flag and quality_flag not in (row.get("quality_flags") or []):
                continue
            if observation_date_from and self._parse_date(row.get("observation_date")) < observation_date_from:
                continue
            if observation_date_to and self._parse_date(row.get("observation_date")) > observation_date_to:
                continue
            items.append(dict(row))

        return items

    def _distinct_values(self, field_name: str) -> list[str]:
        values = {
            str(value)
            for row in self._rows
            if (value := row.get(field_name)) is not None
        }
        return sorted(values)

    def _distinct_quality_flags(self) -> list[str]:
        values = {
            str(flag)
            for row in self._rows
            for flag in row.get("quality_flags", [])
            if flag is not None
        }
        return sorted(values)

    @staticmethod
    def _optional_group_value(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _parse_date(value: Any) -> DateValue:
        if isinstance(value, DateValue):
            return value
        if isinstance(value, str):
            return DateValue.fromisoformat(value)
        raise ValueError("Benchmark seed row contains non-date observation_date.")

    @staticmethod
    def _observation_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        observation_date = item.get("observation_date")
        normalized_date = observation_date or ""
        return (
            observation_date is None,
            normalized_date,
            item.get("variable") or "",
            item.get("plot_id") is None,
            item.get("plot_id") or "",
            item.get("source_sheet") or "",
            item.get("source_row_index") or 0,
            item.get("source_column") or "",
        )


@contextmanager
def patched_nl_query_backend(backend: InMemoryHarmonizedQueryBackend) -> Iterator[None]:
    with patch.object(nl_query_service, "get_harmonized_query_metadata", backend.get_harmonized_query_metadata):
        with patch.object(nl_query_service, "list_harmonized_observations", backend.list_harmonized_observations):
            with patch.object(
                nl_query_service,
                "aggregate_harmonized_observations",
                backend.aggregate_harmonized_observations,
            ):
                yield


def run_benchmark(
    *,
    dataset_path: Path | None = None,
    seed_rows_path: Path | None = None,
    dataset_name: str = DEFAULT_DATASET_NAME,
) -> BenchmarkRunReport:
    dataset = load_benchmark_dataset(dataset_path)
    seed_rows = load_benchmark_seed_rows(seed_rows_path)
    backend = InMemoryHarmonizedQueryBackend(seed_rows)

    question_results = _run_questions(dataset=dataset, backend=backend)
    resolved_dataset_name = dataset_name
    if dataset_path is not None and dataset_path != DEFAULT_BENCHMARK_DATASET_PATH:
        resolved_dataset_name = dataset_path.stem

    return build_benchmark_report(
        dataset_name=resolved_dataset_name,
        results=question_results,
    )


def build_text_summary(report: BenchmarkRunReport) -> str:
    lines = [
        f"Dataset: {report.dataset_name}",
        f"Questions: {report.total_questions}",
        _metric_line("Supported accuracy", report.supported_classification_accuracy),
        _metric_line("Intent accuracy", report.intent_accuracy),
        _metric_line("Result type accuracy", report.result_type_accuracy),
        _metric_line("Query-plan field accuracy", report.query_plan_field_accuracy),
        _metric_line("Result shape accuracy", report.result_shape_accuracy),
        _metric_line("Result content accuracy", report.result_content_accuracy),
        _metric_line("Result accuracy", report.result_accuracy),
        "Error categories:",
    ]

    if report.error_category_counts:
        for error_category, count in sorted(report.error_category_counts.items()):
            lines.append(f"  - {error_category}: {count}")
    else:
        lines.append("  - none")

    return "\n".join(lines)


def build_markdown_summary(report: BenchmarkRunReport) -> str:
    lines = [
        f"# NL Query Benchmark Summary",
        "",
        f"- Dataset: `{report.dataset_name}`",
        f"- Questions: `{report.total_questions}`",
        f"- Supported accuracy: `{report.supported_classification_accuracy.correct}/{report.supported_classification_accuracy.total}` ({report.supported_classification_accuracy.accuracy:.4f})",
        f"- Intent accuracy: `{report.intent_accuracy.correct}/{report.intent_accuracy.total}` ({report.intent_accuracy.accuracy:.4f})",
        f"- Result type accuracy: `{report.result_type_accuracy.correct}/{report.result_type_accuracy.total}` ({report.result_type_accuracy.accuracy:.4f})",
        f"- Query-plan field accuracy: `{report.query_plan_field_accuracy.correct}/{report.query_plan_field_accuracy.total}` ({report.query_plan_field_accuracy.accuracy:.4f})",
        f"- Result shape accuracy: `{report.result_shape_accuracy.correct}/{report.result_shape_accuracy.total}` ({report.result_shape_accuracy.accuracy:.4f})",
        f"- Result content accuracy: `{report.result_content_accuracy.correct}/{report.result_content_accuracy.total}` ({report.result_content_accuracy.accuracy:.4f})",
        f"- Result accuracy: `{report.result_accuracy.correct}/{report.result_accuracy.total}` ({report.result_accuracy.accuracy:.4f})",
        "",
        "## Error Categories",
        "",
    ]

    if report.error_category_counts:
        for error_category, count in sorted(report.error_category_counts.items()):
            lines.append(f"- `{error_category}`: `{count}`")
    else:
        lines.append("- `none`: `0`")

    lines.extend(
        [
            "",
            "## Failed Questions",
            "",
        ]
    )

    failed_questions = [item for item in report.questions if not item.passed]
    if failed_questions:
        for item in failed_questions:
            lines.append(f"- `{item.id}`: `{', '.join(item.error_categories)}`")
    else:
        lines.append("- none")

    return "\n".join(lines)


def _run_questions(
    *,
    dataset: list[BenchmarkQuestion],
    backend: InMemoryHarmonizedQueryBackend,
) -> list[Any]:
    results = []
    with patched_nl_query_backend(backend):
        for question in dataset:
            actual_response = nl_query_service.execute_nl_query(question=question.question)
            results.append(
                evaluate_benchmark_question(
                    question=question,
                    actual_response=actual_response,
                )
            )
    return results


def _metric_line(label: str, metric: Any) -> str:
    return f"{label}: {metric.correct}/{metric.total} ({metric.accuracy:.4f})"

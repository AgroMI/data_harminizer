from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.evaluation.benchmark_dataset import DEFAULT_BENCHMARK_SEED_ROWS_PATH, load_benchmark_seed_rows
from backend.app.evaluation.text_to_sql_benchmark_types import (
    AggregationExpectation,
    ResultExpectation,
    TextToSqlBenchmarkQuestion,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_TEXT_TO_SQL_BENCHMARK_DATASET_PATH = DATA_DIR / "text_to_sql_benchmark_dataset.json"


def load_text_to_sql_benchmark_dataset(path: Path | None = None) -> list[TextToSqlBenchmarkQuestion]:
    dataset_path = path or DEFAULT_TEXT_TO_SQL_BENCHMARK_DATASET_PATH
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {dataset_path}.")
    return [_parse_question(item) for item in payload]


def load_text_to_sql_seed_rows(path: Path | None = None) -> list[dict[str, Any]]:
    return load_benchmark_seed_rows(path or DEFAULT_BENCHMARK_SEED_ROWS_PATH)


def _parse_question(payload: Any) -> TextToSqlBenchmarkQuestion:
    if not isinstance(payload, dict):
        raise ValueError("Benchmark question payload must be an object.")
    expected_result_payload = payload.get("expected_result") or {}
    if not isinstance(expected_result_payload, dict):
        raise ValueError("expected_result must be an object.")

    return TextToSqlBenchmarkQuestion(
        id=_required_str(payload, "id"),
        category=_required_str(payload, "category"),
        question=_required_str(payload, "question"),
        expected_status=_required_str(payload, "expected_status"),
        expected_intent=_required_str(payload, "expected_intent"),
        expected_result_type=_required_str(payload, "expected_result_type"),
        expected_query_plan=dict(payload.get("expected_query_plan") or {}),
        expected_result=_parse_expected_result(expected_result_payload),
        expected_sql_valid=bool(payload.get("expected_sql_valid", False)),
        unsafe=bool(payload.get("unsafe", False)),
        notes=_optional_str(payload.get("notes")),
    )


def _parse_expected_result(payload: dict[str, Any]) -> ResultExpectation:
    record_keys = payload.get("record_keys") or []
    aggregation_items = payload.get("aggregation_items") or []
    if not isinstance(record_keys, list) or not isinstance(aggregation_items, list):
        raise ValueError("expected_result must contain record_keys and aggregation_items lists.")
    return ResultExpectation(
        record_keys=tuple(str(item) for item in record_keys),
        aggregation_items=tuple(
            AggregationExpectation(
                group_value=item.get("group_value"),
                metric_value=item["metric_value"],
                record_count=item.get("record_count"),
                normalized_unit=item.get("normalized_unit"),
            )
            for item in aggregation_items
        ),
        count=payload.get("count"),
    )


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional string field must be a string when present.")
    return value or None

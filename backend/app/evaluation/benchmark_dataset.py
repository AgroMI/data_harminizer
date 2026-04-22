from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.evaluation.benchmark_types import (
    AggregationExpectation,
    BenchmarkQuestion,
    QueryPlanExpectation,
    ResultExpectation,
    TopGroupExpectation,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_BENCHMARK_DATASET_PATH = DATA_DIR / "nl_query_benchmark_dataset.json"
DEFAULT_BENCHMARK_SEED_ROWS_PATH = DATA_DIR / "nl_query_benchmark_seed_rows.json"


def load_benchmark_dataset(path: Path | None = None) -> list[BenchmarkQuestion]:
    dataset_path = path or DEFAULT_BENCHMARK_DATASET_PATH
    payload = _load_json_list(dataset_path)
    return [_parse_benchmark_question(item) for item in payload]


def load_benchmark_seed_rows(path: Path | None = None) -> list[dict[str, Any]]:
    seed_path = path or DEFAULT_BENCHMARK_SEED_ROWS_PATH
    payload = _load_json_list(seed_path)
    rows: list[dict[str, Any]] = []

    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Seed row #{index} must be an object.")
        rows.append(dict(item))

    return rows


def _load_json_list(path: Path) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list in {path}.")
    return payload


def _parse_benchmark_question(payload: Any) -> BenchmarkQuestion:
    if not isinstance(payload, dict):
        raise ValueError("Benchmark question payload must be an object.")

    expected_result_payload = payload.get("expected_result") or {}
    if not isinstance(expected_result_payload, dict):
        raise ValueError("expected_result must be an object.")

    return BenchmarkQuestion(
        id=_read_required_str(payload, "id"),
        question=_read_required_str(payload, "question"),
        expected_supported=_read_required_bool(payload, "expected_supported"),
        expected_intent_type=_read_required_str(payload, "expected_intent_type"),
        expected_result_type=_read_required_str(payload, "expected_result_type"),
        expected_query_plan=_parse_query_plan_expectation(payload.get("expected_query_plan") or {}),
        expected_result=_parse_result_expectation(expected_result_payload),
        notes=_read_optional_str(payload.get("notes")),
    )


def _parse_query_plan_expectation(payload: Any) -> QueryPlanExpectation:
    if not isinstance(payload, dict):
        raise ValueError("expected_query_plan must be an object.")

    filters = payload.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("expected_query_plan.filters must be an object.")

    return QueryPlanExpectation(
        variable=_read_optional_str(payload.get("variable")),
        group_by=_read_optional_str(payload.get("group_by")),
        metric=_read_optional_str(payload.get("metric")),
        include_invalid=_read_optional_bool(payload.get("include_invalid")),
        filters=dict(filters),
    )


def _parse_result_expectation(payload: dict[str, Any]) -> ResultExpectation:
    record_keys = payload.get("record_keys") or []
    aggregation_items = payload.get("aggregation_items") or []
    top_group_payload = payload.get("top_group")

    if not isinstance(record_keys, list):
        raise ValueError("expected_result.record_keys must be a list.")
    if not isinstance(aggregation_items, list):
        raise ValueError("expected_result.aggregation_items must be a list.")

    return ResultExpectation(
        record_keys=tuple(_read_str_list(record_keys, "expected_result.record_keys")),
        aggregation_items=tuple(_parse_aggregation_expectation(item) for item in aggregation_items),
        top_group=_parse_top_group_expectation(top_group_payload),
        count=_read_optional_int(payload.get("count")),
    )


def _parse_aggregation_expectation(payload: Any) -> AggregationExpectation:
    if not isinstance(payload, dict):
        raise ValueError("Aggregation expectation must be an object.")

    return AggregationExpectation(
        group_value=_read_optional_str(payload.get("group_value")),
        metric_value=_read_required_number(payload, "metric_value"),
        record_count=_read_optional_int(payload.get("record_count")),
        normalized_unit=_read_optional_str(payload.get("normalized_unit")),
    )


def _parse_top_group_expectation(payload: Any) -> TopGroupExpectation | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("expected_result.top_group must be an object.")

    return TopGroupExpectation(
        group_value=_read_optional_str(payload.get("group_value")),
        metric_value=_read_required_number(payload, "metric_value"),
        record_count=_read_optional_int(payload.get("record_count")),
        normalized_unit=_read_optional_str(payload.get("normalized_unit")),
    )


def _read_required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _read_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional string field must be a string when present.")
    cleaned = value.strip()
    return cleaned or None


def _read_required_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value


def _read_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("Optional boolean field must be a boolean when present.")
    return value


def _read_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError("Optional integer field must be an integer when present.")
    return value


def _read_required_number(payload: dict[str, Any], key: str) -> float | int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric.")
    return value


def _read_str_list(values: list[Any], label: str) -> list[str]:
    result: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} must only contain non-empty strings.")
        result.append(item)
    return result

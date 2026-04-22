from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.app.evaluation.benchmark_types import (
    AccuracyMetric,
    BenchmarkQuestion,
    BenchmarkQuestionResult,
    BenchmarkRunReport,
    ErrorCategory,
    FieldComparison,
)

FLOAT_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class ResultEvaluation:
    shape_match: bool
    content_match: bool
    error_categories: tuple[ErrorCategory, ...]


def evaluate_benchmark_question(
    *,
    question: BenchmarkQuestion,
    actual_response: dict[str, Any],
) -> BenchmarkQuestionResult:
    actual_supported = bool(actual_response.get("supported"))
    actual_query_plan = _ensure_dict(actual_response.get("query_plan"))
    actual_intent_type = _optional_str(actual_query_plan.get("intent_type"))
    actual_result_type = _optional_str(actual_response.get("result_type"))

    plan_comparisons = compare_query_plan(question=question, actual_response=actual_response)
    result_evaluation = evaluate_result(question=question, actual_response=actual_response)

    error_categories: list[ErrorCategory] = []
    if not plan_comparisons["supported"].matched:
        error_categories.append("unsupported_misclassification")
    if not plan_comparisons["intent_type"].matched:
        error_categories.append("wrong_intent_type")
    if "group_by" in plan_comparisons and not plan_comparisons["group_by"].matched:
        error_categories.append("wrong_group_by")
    if "metric" in plan_comparisons and not plan_comparisons["metric"].matched:
        error_categories.append("wrong_metric")
    if any(
        field_name.startswith("filters.") and not comparison.matched
        for field_name, comparison in plan_comparisons.items()
    ):
        error_categories.append("wrong_filter")
    error_categories.extend(result_evaluation.error_categories)

    unique_categories = tuple(dict.fromkeys(error_categories))
    plan_field_matches = {
        field_name: comparison.matched
        for field_name, comparison in plan_comparisons.items()
    }
    result_type_match = plan_comparisons["result_type"].matched
    result_match = result_evaluation.shape_match and result_evaluation.content_match
    passed = (
        all(plan_field_matches.values())
        and result_evaluation.shape_match
        and result_evaluation.content_match
    )

    return BenchmarkQuestionResult(
        id=question.id,
        question=question.question,
        passed=passed,
        supported_match=plan_field_matches["supported"],
        intent_match=plan_field_matches["intent_type"],
        result_type_match=result_type_match,
        plan_field_matches=plan_field_matches,
        result_shape_match=result_evaluation.shape_match,
        result_content_match=result_evaluation.content_match,
        result_match=result_match,
        error_categories=unique_categories,
        actual_supported=actual_supported,
        actual_intent_type=actual_intent_type,
        actual_result_type=actual_result_type,
        actual_query_plan=actual_query_plan,
        notes=question.notes,
    )


def compare_query_plan(
    *,
    question: BenchmarkQuestion,
    actual_response: dict[str, Any],
) -> dict[str, FieldComparison]:
    actual_query_plan = _ensure_dict(actual_response.get("query_plan"))
    actual_filters = _ensure_dict(actual_query_plan.get("filters"))
    expected_query_plan = question.expected_query_plan

    comparisons: dict[str, FieldComparison] = {
        "supported": _compare_field(
            "supported",
            question.expected_supported,
            bool(actual_response.get("supported")),
        ),
        "intent_type": _compare_field(
            "intent_type",
            question.expected_intent_type,
            _optional_str(actual_query_plan.get("intent_type")),
        ),
        "result_type": _compare_field(
            "result_type",
            question.expected_result_type,
            _optional_str(actual_response.get("result_type")),
        ),
    }

    optional_fields = {
        "variable": expected_query_plan.variable,
        "group_by": expected_query_plan.group_by,
        "metric": expected_query_plan.metric,
        "include_invalid": expected_query_plan.include_invalid,
    }
    for field_name, expected_value in optional_fields.items():
        if expected_value is None:
            continue
        comparisons[field_name] = _compare_field(
            field_name,
            expected_value,
            actual_query_plan.get(field_name),
        )

    for filter_name, expected_value in expected_query_plan.filters.items():
        comparisons[f"filters.{filter_name}"] = _compare_field(
            f"filters.{filter_name}",
            expected_value,
            actual_filters.get(filter_name),
        )

    return comparisons


def evaluate_result(
    *,
    question: BenchmarkQuestion,
    actual_response: dict[str, Any],
) -> ResultEvaluation:
    actual_results = _ensure_dict(actual_response.get("results"))
    actual_result_type = _optional_str(actual_response.get("result_type"))

    shape_match = _matches_expected_result_shape(
        expected_result_type=question.expected_result_type,
        actual_result_type=actual_result_type,
        actual_results=actual_results,
    )
    if not shape_match:
        return ResultEvaluation(
            shape_match=False,
            content_match=False,
            error_categories=("wrong_result_shape",),
        )

    if question.expected_result_type == "records":
        content_match = _matches_expected_record_keys(question=question, actual_results=actual_results)
        return ResultEvaluation(
            shape_match=True,
            content_match=content_match,
            error_categories=() if content_match else ("wrong_result_content",),
        )

    if question.expected_result_type == "aggregation":
        content_match = _matches_expected_aggregations(question=question, actual_results=actual_results)
        return ResultEvaluation(
            shape_match=True,
            content_match=content_match,
            error_categories=() if content_match else ("wrong_result_content",),
        )

    if question.expected_result_type == "top_group":
        content_match = _matches_expected_top_group(question=question, actual_results=actual_results)
        return ResultEvaluation(
            shape_match=True,
            content_match=content_match,
            error_categories=() if content_match else ("wrong_top_group",),
        )

    content_match = _matches_unsupported_result(question=question, actual_results=actual_results)
    return ResultEvaluation(
        shape_match=True,
        content_match=content_match,
        error_categories=() if content_match else ("wrong_result_content",),
    )


def build_benchmark_report(
    *,
    dataset_name: str,
    results: list[BenchmarkQuestionResult],
) -> BenchmarkRunReport:
    total_questions = len(results)
    field_breakdown = _build_plan_field_breakdown(results)
    error_category_counts = Counter(
        error_category
        for result in results
        for error_category in result.error_categories
    )

    return BenchmarkRunReport(
        dataset_name=dataset_name,
        total_questions=total_questions,
        supported_classification_accuracy=_metric_from_booleans(
            [result.supported_match for result in results]
        ),
        intent_accuracy=_metric_from_booleans(
            [result.intent_match for result in results]
        ),
        result_type_accuracy=_metric_from_booleans(
            [result.result_type_match for result in results]
        ),
        query_plan_field_accuracy=_metric_from_booleans(
            [
                matched
                for result in results
                for field_name, matched in result.plan_field_matches.items()
                if field_name not in {"supported", "intent_type", "result_type"}
            ]
        ),
        result_shape_accuracy=_metric_from_booleans(
            [result.result_shape_match for result in results]
        ),
        result_content_accuracy=_metric_from_booleans(
            [result.result_content_match for result in results]
        ),
        result_accuracy=_metric_from_booleans(
            [result.result_match for result in results]
        ),
        plan_field_breakdown=field_breakdown,
        error_category_counts=dict(error_category_counts),
        questions=results,
    )


def _matches_expected_result_shape(
    *,
    expected_result_type: str,
    actual_result_type: str | None,
    actual_results: dict[str, Any],
) -> bool:
    if actual_result_type != expected_result_type:
        return False

    records = actual_results.get("records")
    aggregations = actual_results.get("aggregations")
    top_group = actual_results.get("top_group")

    if expected_result_type == "records":
        return isinstance(records, list) and isinstance(aggregations, list) and not aggregations and top_group is None
    if expected_result_type == "aggregation":
        return isinstance(aggregations, list) and isinstance(records, list) and not records and top_group is None
    if expected_result_type == "top_group":
        return isinstance(aggregations, list) and isinstance(records, list) and not records and isinstance(top_group, dict)
    if expected_result_type == "unsupported":
        return (
            isinstance(records, list)
            and isinstance(aggregations, list)
            and not records
            and not aggregations
            and top_group is None
        )
    return False


def _matches_expected_record_keys(
    *,
    question: BenchmarkQuestion,
    actual_results: dict[str, Any],
) -> bool:
    actual_records = actual_results.get("records")
    if not isinstance(actual_records, list):
        return False

    actual_keys = {_record_key(item) for item in actual_records if isinstance(item, dict)}
    expected_keys = set(question.expected_result.record_keys)
    expected_count = question.expected_result.count

    if expected_count is not None and len(actual_records) != expected_count:
        return False
    return actual_keys == expected_keys


def _matches_expected_aggregations(
    *,
    question: BenchmarkQuestion,
    actual_results: dict[str, Any],
) -> bool:
    actual_items = actual_results.get("aggregations")
    if not isinstance(actual_items, list):
        return False

    expected_items = question.expected_result.aggregation_items
    expected_count = question.expected_result.count
    if expected_count is not None and len(actual_items) != expected_count:
        return False
    if len(actual_items) != len(expected_items):
        return False

    actual_by_group = {
        _aggregation_group_value(item): item
        for item in actual_items
        if isinstance(item, dict)
    }
    if len(actual_by_group) != len(expected_items):
        return False

    for expected_item in expected_items:
        actual_item = actual_by_group.get(expected_item.group_value)
        if actual_item is None:
            return False
        if not _matches_metric_value(actual_item.get("metric_value"), expected_item.metric_value):
            return False
        if expected_item.record_count is not None and actual_item.get("record_count") != expected_item.record_count:
            return False
        if expected_item.normalized_unit is not None and actual_item.get("normalized_unit") != expected_item.normalized_unit:
            return False

    return True


def _matches_expected_top_group(
    *,
    question: BenchmarkQuestion,
    actual_results: dict[str, Any],
) -> bool:
    expected_top_group = question.expected_result.top_group
    actual_top_group = actual_results.get("top_group")
    if expected_top_group is None or not isinstance(actual_top_group, dict):
        return False

    if actual_top_group.get("group_value") != expected_top_group.group_value:
        return False
    if not _matches_metric_value(actual_top_group.get("metric_value"), expected_top_group.metric_value):
        return False
    if expected_top_group.record_count is not None and actual_top_group.get("record_count") != expected_top_group.record_count:
        return False
    if expected_top_group.normalized_unit is not None and actual_top_group.get("normalized_unit") != expected_top_group.normalized_unit:
        return False

    expected_count = question.expected_result.count
    if expected_count is not None and actual_results.get("count") != expected_count:
        return False
    return True


def _matches_unsupported_result(
    *,
    question: BenchmarkQuestion,
    actual_results: dict[str, Any],
) -> bool:
    expected_count = question.expected_result.count
    if expected_count is None:
        return True
    return actual_results.get("count") == expected_count


def _compare_field(field_name: str, expected: Any, actual: Any) -> FieldComparison:
    return FieldComparison(
        field_name=field_name,
        expected=expected,
        actual=actual,
        matched=_values_match(expected, actual),
    )


def _values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        return tuple(expected) == tuple(actual or [])
    if isinstance(expected, float):
        return _matches_metric_value(actual, expected)
    return expected == actual


def _matches_metric_value(actual: Any, expected: float | int) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    return abs(float(actual) - float(expected)) <= FLOAT_TOLERANCE


def _record_key(item: dict[str, Any]) -> str:
    return (
        f"{item.get('upload_session_id')}|{item.get('source_sheet')}|"
        f"{item.get('source_row_index')}|{item.get('source_column')}"
    )


def _aggregation_group_value(item: dict[str, Any]) -> str | None:
    group_value = item.get("group_value")
    if group_value is None:
        return None
    return str(group_value)


def _build_plan_field_breakdown(results: list[BenchmarkQuestionResult]) -> dict[str, AccuracyMetric]:
    field_values: dict[str, list[bool]] = {}
    for result in results:
        for field_name, matched in result.plan_field_matches.items():
            field_values.setdefault(field_name, []).append(matched)

    return {
        field_name: _metric_from_booleans(values)
        for field_name, values in sorted(field_values.items())
    }


def _metric_from_booleans(values: list[bool]) -> AccuracyMetric:
    return AccuracyMetric(correct=sum(1 for value in values if value), total=len(values))


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

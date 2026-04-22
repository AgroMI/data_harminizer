from __future__ import annotations

from typing import Any

from backend.app.evaluation.text_to_sql_benchmark_types import (
    AccuracyMetric,
    TextToSqlBenchmarkQuestion,
    TextToSqlBenchmarkQuestionResult,
    TextToSqlBenchmarkReport,
)


def evaluate_question(
    *,
    question: TextToSqlBenchmarkQuestion,
    actual_response: dict[str, Any],
) -> TextToSqlBenchmarkQuestionResult:
    actual_plan = dict(actual_response.get("query_plan") or {})
    actual_status = str(actual_response.get("status") or "unsupported")
    actual_intent = str(actual_plan.get("intent") or "unsupported")
    actual_result_type = str(actual_response.get("result_type") or "unsupported")
    actual_sql_valid = bool((actual_response.get("validation") or {}).get("valid"))
    actual_execution = actual_response.get("execution")

    query_plan_match = (
        actual_status == question.expected_status
        and actual_intent == question.expected_intent
        and actual_result_type == question.expected_result_type
        and _matches_expected_plan_subset(question.expected_query_plan, actual_plan)
    )
    sql_valid_match = actual_sql_valid == question.expected_sql_valid
    execution_success = bool(actual_execution) == (question.expected_status == "supported" and question.expected_sql_valid)
    answer_match = _matches_expected_answer(question=question, actual_response=actual_response)
    unsupported_match = (
        question.expected_status == "supported"
        or actual_status == question.expected_status
    )
    unsafe_rejection_match = (not question.unsafe) or (actual_status != "supported" and actual_response.get("execution") is None)

    return TextToSqlBenchmarkQuestionResult(
        id=question.id,
        category=question.category,
        question=question.question,
        passed=query_plan_match and sql_valid_match and execution_success and answer_match and unsafe_rejection_match,
        query_plan_match=query_plan_match,
        sql_valid_match=sql_valid_match,
        execution_success=execution_success,
        answer_match=answer_match,
        unsupported_match=unsupported_match,
        unsafe_rejection_match=unsafe_rejection_match,
        actual_status=actual_status,
        actual_intent=actual_intent,
        actual_result_type=actual_result_type,
        actual_sql_valid=actual_sql_valid,
        notes=question.notes,
    )


def build_report(
    *,
    dataset_name: str,
    results: list[TextToSqlBenchmarkQuestionResult],
    questions: list[TextToSqlBenchmarkQuestion],
) -> TextToSqlBenchmarkReport:
    question_by_id = {question.id: question for question in questions}
    unsupported_results = [item for item in results if question_by_id[item.id].expected_status != "supported"]
    unsafe_results = [item for item in results if question_by_id[item.id].unsafe]

    return TextToSqlBenchmarkReport(
        dataset_name=dataset_name,
        total_questions=len(results),
        query_plan_correctness=_metric([item.query_plan_match for item in results]),
        sql_validity_rate=_metric([item.sql_valid_match for item in results]),
        execution_success_rate=_metric([item.execution_success for item in results]),
        answer_correctness=_metric([item.answer_match for item in results]),
        unsupported_query_rate=_metric([item.unsupported_match for item in unsupported_results]),
        rejected_unsafe_query_rate=_metric([item.unsafe_rejection_match for item in unsafe_results]),
        questions=results,
    )


def _matches_expected_plan_subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if isinstance(expected_value, dict):
            actual_value = actual.get(key) or {}
            if not isinstance(actual_value, dict):
                return False
            if not _matches_expected_plan_subset(expected_value, actual_value):
                return False
            continue
        if actual.get(key) != expected_value:
            return False
    return True


def _matches_expected_answer(
    *,
    question: TextToSqlBenchmarkQuestion,
    actual_response: dict[str, Any],
) -> bool:
    if question.expected_status != "supported":
        return actual_response.get("execution") is None

    answer = actual_response.get("answer") or {}
    if question.expected_result_type == "records":
        records = list(answer.get("records") or [])
        actual_record_keys = tuple(
            f"{item.get('plot_id')}|{item.get('variable')}|{item.get('validation_status')}"
            for item in records
        )
        return (
            actual_record_keys == question.expected_result.record_keys
            and answer.get("count") == question.expected_result.count
        )

    if question.expected_result_type == "aggregation":
        items = list(answer.get("items") or [])
        if answer.get("count") != question.expected_result.count:
            return False
        actual_items = [
            (
                item.get("group_value"),
                item.get("metric_value"),
                item.get("record_count"),
                item.get("normalized_unit"),
            )
            for item in items
        ]
        expected_items = [
            (
                item.group_value,
                item.metric_value,
                item.record_count,
                item.normalized_unit,
            )
            for item in question.expected_result.aggregation_items
        ]
        return actual_items == expected_items

    return True


def _metric(matches: list[bool]) -> AccuracyMetric:
    return AccuracyMetric(correct=sum(1 for item in matches if item), total=len(matches))

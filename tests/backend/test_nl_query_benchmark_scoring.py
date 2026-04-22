from __future__ import annotations

from backend.app.evaluation.benchmark_scoring import (
    compare_query_plan,
    evaluate_benchmark_question,
)
from backend.app.evaluation.benchmark_types import (
    BenchmarkQuestion,
    QueryPlanExpectation,
    ResultExpectation,
    TopGroupExpectation,
)


def test_compare_query_plan_matches_structured_subset_fields() -> None:
    question = BenchmarkQuestion(
        id="q1",
        question="What is the average yield by variety?",
        expected_supported=True,
        expected_intent_type="aggregate",
        expected_result_type="aggregation",
        expected_query_plan=QueryPlanExpectation(
            variable="yield",
            group_by="variety",
            metric="avg_normalized_value",
            include_invalid=False,
            filters={
                "variable": "yield",
                "normalized_unit": "kg/ha",
            },
        ),
    )
    actual_response = {
        "supported": True,
        "result_type": "aggregation",
        "query_plan": {
            "intent_type": "aggregate",
            "variable": "yield",
            "group_by": "variety",
            "metric": "avg_normalized_value",
            "include_invalid": False,
            "filters": {
                "variable": "yield",
                "normalized_unit": "kg/ha",
                "location": None,
            },
        },
    }

    comparisons = compare_query_plan(question=question, actual_response=actual_response)

    assert all(comparison.matched for comparison in comparisons.values())
    assert comparisons["filters.normalized_unit"].actual == "kg/ha"


def test_evaluate_benchmark_question_reports_plan_and_result_errors() -> None:
    question = BenchmarkQuestion(
        id="q2",
        question="Which variety has the highest average yield?",
        expected_supported=True,
        expected_intent_type="top_group",
        expected_result_type="top_group",
        expected_query_plan=QueryPlanExpectation(
            variable="yield",
            group_by="variety",
            metric="avg_normalized_value",
            include_invalid=False,
            filters={
                "variable": "yield",
                "location": "north",
                "normalized_unit": "kg/ha",
            },
        ),
        expected_result=ResultExpectation(
            top_group=TopGroupExpectation(
                group_value="Apex",
                metric_value=13500.0,
                record_count=2,
                normalized_unit="kg/ha",
            ),
            count=2,
        ),
    )
    actual_response = {
        "supported": True,
        "result_type": "top_group",
        "query_plan": {
            "intent_type": "aggregate",
            "variable": "yield",
            "group_by": "treatment",
            "metric": "count",
            "include_invalid": False,
            "filters": {
                "variable": "yield",
                "location": "south",
                "normalized_unit": "kg/ha",
            },
        },
        "results": {
            "records": [],
            "aggregations": [
                {
                    "group_value": "treated",
                    "metric_value": 2,
                    "record_count": 2,
                    "normalized_unit": None,
                }
            ],
            "top_group": {
                "group_value": "treated",
                "metric_value": 2,
                "record_count": 2,
                "normalized_unit": None,
            },
            "count": 1,
        },
    }

    result = evaluate_benchmark_question(question=question, actual_response=actual_response)

    assert result.passed is False
    assert result.intent_match is False
    assert result.plan_field_matches["group_by"] is False
    assert result.plan_field_matches["metric"] is False
    assert result.plan_field_matches["filters.location"] is False
    assert set(result.error_categories) == {
        "wrong_intent_type",
        "wrong_group_by",
        "wrong_metric",
        "wrong_filter",
        "wrong_top_group",
    }


def test_evaluate_benchmark_question_reports_unsupported_misclassification() -> None:
    question = BenchmarkQuestion(
        id="q3",
        question="Draw a chart",
        expected_supported=False,
        expected_intent_type="unsupported",
        expected_result_type="unsupported",
        expected_result=ResultExpectation(count=0),
    )
    actual_response = {
        "supported": True,
        "result_type": "records",
        "query_plan": {
            "intent_type": "list_records",
            "filters": {},
        },
        "results": {
            "records": [{"upload_session_id": "u1", "source_sheet": "S", "source_row_index": 1, "source_column": "c"}],
            "aggregations": [],
            "top_group": None,
            "count": 1,
        },
    }

    result = evaluate_benchmark_question(question=question, actual_response=actual_response)

    assert result.supported_match is False
    assert "unsupported_misclassification" in result.error_categories
    assert "wrong_intent_type" in result.error_categories
    assert "wrong_result_shape" in result.error_categories

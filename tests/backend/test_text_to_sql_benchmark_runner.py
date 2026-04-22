from __future__ import annotations

from backend.app.evaluation.text_to_sql_benchmark_runner import run_text_to_sql_benchmark


def test_text_to_sql_benchmark_runner_produces_metrics() -> None:
    report = run_text_to_sql_benchmark()

    assert report.total_questions >= 50
    assert report.query_plan_correctness.total == report.total_questions
    assert report.sql_validity_rate.total == report.total_questions
    assert report.execution_success_rate.total == report.total_questions
    assert report.answer_correctness.total == report.total_questions
    assert report.unsupported_query_rate.total >= 1
    assert report.rejected_unsafe_query_rate.total >= 1

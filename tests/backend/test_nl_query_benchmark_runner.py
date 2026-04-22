from __future__ import annotations

import json
from pathlib import Path

from backend.app.evaluation.benchmark_runner import (
    build_markdown_summary,
    build_text_summary,
    run_benchmark,
)
from backend.app.evaluation.benchmark_types import BenchmarkRunReport


def test_run_benchmark_returns_expected_summary_fields_for_mini_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "mini_benchmark_dataset.json"
    seed_rows_path = tmp_path / "mini_benchmark_seed_rows.json"

    dataset_path.write_text(
        json.dumps(
            [
                {
                    "id": "aggregate_yield_by_variety",
                    "question": "What is the average yield by variety?",
                    "expected_supported": True,
                    "expected_intent_type": "aggregate",
                    "expected_result_type": "aggregation",
                    "expected_query_plan": {
                        "variable": "yield",
                        "group_by": "variety",
                        "metric": "avg_normalized_value",
                        "include_invalid": False,
                        "filters": {
                            "variable": "yield",
                            "normalized_unit": "kg/ha",
                        },
                    },
                    "expected_result": {
                        "count": 2,
                        "aggregation_items": [
                            {
                                "group_value": "Apex",
                                "metric_value": 13500.0,
                                "record_count": 2,
                                "normalized_unit": "kg/ha",
                            },
                            {
                                "group_value": "Nova",
                                "metric_value": 11000.0,
                                "record_count": 1,
                                "normalized_unit": "kg/ha",
                            },
                        ],
                    },
                },
                {
                    "id": "unsupported_chart_request",
                    "question": "Rajzolj diagramot a teljes trendrol.",
                    "expected_supported": False,
                    "expected_intent_type": "unsupported",
                    "expected_result_type": "unsupported",
                    "expected_result": {
                        "count": 0,
                    },
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    seed_rows_path.write_text(
        json.dumps(
            [
                {
                    "upload_session_id": "u1",
                    "observation_date": "2026-05-01",
                    "plot_id": "P1",
                    "variety": "Apex",
                    "treatment": "control",
                    "location": "north",
                    "variable": "yield",
                    "value": 12.0,
                    "unit": "t/ha",
                    "normalized_value": 12000.0,
                    "normalized_unit": "kg/ha",
                    "validation_status": "valid",
                    "quality_flags": [],
                    "source_sheet": "FieldData",
                    "source_row_index": 2,
                    "source_column": "yield_t/ha",
                },
                {
                    "upload_session_id": "u1",
                    "observation_date": "2026-05-02",
                    "plot_id": "P2",
                    "variety": "Apex",
                    "treatment": "treated",
                    "location": "north",
                    "variable": "yield",
                    "value": 15.0,
                    "unit": "t/ha",
                    "normalized_value": 15000.0,
                    "normalized_unit": "kg/ha",
                    "validation_status": "warning",
                    "quality_flags": ["outlier_candidate"],
                    "source_sheet": "FieldData",
                    "source_row_index": 3,
                    "source_column": "yield_t/ha",
                },
                {
                    "upload_session_id": "u2",
                    "observation_date": "2026-05-04",
                    "plot_id": "P4",
                    "variety": "Nova",
                    "treatment": "treated",
                    "location": "south",
                    "variable": "yield",
                    "value": 11000.0,
                    "unit": "kg/ha",
                    "normalized_value": 11000.0,
                    "normalized_unit": "kg/ha",
                    "validation_status": "valid",
                    "quality_flags": [],
                    "source_sheet": "FieldData",
                    "source_row_index": 2,
                    "source_column": "yield_kg_ha",
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    report = run_benchmark(
        dataset_path=dataset_path,
        seed_rows_path=seed_rows_path,
    )

    assert isinstance(report, BenchmarkRunReport)
    assert report.dataset_name == "mini_benchmark_dataset"
    assert report.total_questions == 2
    assert report.supported_classification_accuracy.correct == 2
    assert report.intent_accuracy.correct == 2
    assert report.query_plan_field_accuracy.correct == report.query_plan_field_accuracy.total
    assert report.result_accuracy.correct == 2
    assert all(item.passed for item in report.questions)


def test_benchmark_summary_renderers_include_key_metrics() -> None:
    report = run_benchmark()

    text_summary = build_text_summary(report)
    markdown_summary = build_markdown_summary(report)

    assert "Dataset: nl_query_mvp_golden_v1" in text_summary
    assert "Supported accuracy:" in text_summary
    assert "# NL Query Benchmark Summary" in markdown_summary
    assert "- Dataset: `nl_query_mvp_golden_v1`" in markdown_summary
    assert "## Failed Questions" in markdown_summary

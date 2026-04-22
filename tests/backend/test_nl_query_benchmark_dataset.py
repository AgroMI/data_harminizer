from __future__ import annotations

from backend.app.evaluation.benchmark_dataset import (
    load_benchmark_dataset,
    load_benchmark_seed_rows,
)


def test_benchmark_dataset_loads_expected_questions() -> None:
    dataset = load_benchmark_dataset()

    assert len(dataset) == 25
    assert {item.id for item in dataset} >= {
        "aggregate_yield_by_variety_hu",
        "top_group_treatment_hu",
        "list_warning_and_invalid_hu",
        "unsupported_chart_request_hu",
    }

    aggregate_question = next(item for item in dataset if item.id == "aggregate_yield_by_variety_hu")
    assert aggregate_question.expected_supported is True
    assert aggregate_question.expected_intent_type == "aggregate"
    assert aggregate_question.expected_result_type == "aggregation"
    assert aggregate_question.expected_query_plan.group_by == "variety"
    assert aggregate_question.expected_query_plan.metric == "avg_normalized_value"
    assert aggregate_question.expected_result.count == 2
    assert aggregate_question.expected_result.aggregation_items[0].group_value == "Apex"


def test_benchmark_seed_rows_load_controlled_fixture_rows() -> None:
    rows = load_benchmark_seed_rows()

    assert len(rows) == 6
    assert rows[0]["variable"] == "yield"
    assert rows[0]["normalized_unit"] == "kg/ha"
    assert rows[1]["validation_status"] == "warning"
    assert rows[2]["validation_status"] == "invalid"
    assert rows[-1]["variable"] == "plant_height"

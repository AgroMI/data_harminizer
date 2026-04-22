from __future__ import annotations

from backend.app.evaluation.text_to_sql_benchmark_dataset import load_text_to_sql_benchmark_dataset


def test_text_to_sql_benchmark_dataset_is_large_and_diverse() -> None:
    dataset = load_text_to_sql_benchmark_dataset()
    assert len(dataset) >= 50
    categories = {item.category for item in dataset}
    assert {"aggregation", "records", "unsafe", "clarification"} <= categories
    assert any(item.unsafe for item in dataset)

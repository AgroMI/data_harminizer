from __future__ import annotations

from etl.preview_schema import classify_block_semantics


def test_classify_block_semantics_marks_observation_like_blocks() -> None:
    block = {
        "block_id": "S1_B1",
        "type_suggestions": [
            {
                "column": "column_1",
                "semantic_role": "dimension",
                "canonical_dimension": "variety",
                "canonical_measure": None,
                "unit": None,
            },
            {
                "column": "column_2",
                "semantic_role": "dimension",
                "canonical_dimension": "replicate",
                "canonical_measure": None,
                "unit": None,
            },
            {
                "column": "n_0_a",
                "semantic_role": "measure",
                "canonical_dimension": None,
                "canonical_measure": "yield",
                "unit": "kg/parc",
            },
            {
                "column": "n_40_b",
                "semantic_role": "measure",
                "canonical_dimension": None,
                "canonical_measure": "yield",
                "unit": "kg/parc",
            },
        ],
    }

    semantics = classify_block_semantics(block)

    assert semantics["semantic_classification"] == "observation_like"
    assert semantics["commit_decision"] == "commit_observations"
    assert semantics["skip_reason"] is None


def test_classify_block_semantics_marks_summary_like_blocks() -> None:
    block = {
        "block_id": "S1_B99",
        "type_suggestions": [
            {
                "column": "column_1",
                "semantic_role": "ignore",
                "canonical_dimension": None,
                "canonical_measure": None,
                "unit": None,
            },
            *[
                {
                    "column": column,
                    "semantic_role": "measure",
                    "canonical_dimension": None,
                    "canonical_measure": None,
                    "unit": None,
                }
                for column in ("a", "b", "c", "d")
            ],
        ],
    }

    semantics = classify_block_semantics(block)

    assert semantics["semantic_classification"] == "summary_like"
    assert semantics["commit_decision"] == "skip_summary_block"
    assert semantics["skip_reason"] == "summary_like_block"


def test_classify_block_semantics_is_conservative_for_weak_blocks() -> None:
    block = {
        "block_id": "S1_B50",
        "type_suggestions": [
            {
                "column": "plot",
                "semantic_role": "dimension",
                "canonical_dimension": "plot_id",
                "canonical_measure": None,
                "unit": None,
            },
            {
                "column": "value_1",
                "semantic_role": "measure",
                "canonical_dimension": None,
                "canonical_measure": None,
                "unit": None,
            },
        ],
    }

    semantics = classify_block_semantics(block)

    assert semantics["semantic_classification"] == "unknown"
    assert semantics["commit_decision"] == "commit_observations"
    assert semantics["skip_reason"] is None

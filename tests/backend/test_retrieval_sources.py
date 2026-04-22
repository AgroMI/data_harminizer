from __future__ import annotations

from backend.app.retrieval.retrieval_sources import (
    build_raw_context_documents,
    build_schema_documents,
)


def test_build_raw_context_documents_creates_structured_documents() -> None:
    upload_detail = {
        "id": "u1",
        "preview": {
            "block_count": 1,
            "blocks": [
                {
                    "block_id": "S1_B1",
                    "sheet": "FieldData",
                    "range": "A1:G5",
                    "headers": ["date", "plot_id", "yield_t/ha"],
                    "type_suggestions": [
                        {
                            "column": "date",
                            "semantic_role": "date",
                            "canonical_measure": None,
                            "canonical_dimension": None,
                            "warnings": [],
                        },
                        {
                            "column": "plot_id",
                            "semantic_role": "dimension",
                            "canonical_measure": None,
                            "canonical_dimension": "plot_id",
                            "warnings": [],
                        },
                        {
                            "column": "yield_t/ha",
                            "semantic_role": "measure",
                            "canonical_measure": "yield",
                            "canonical_dimension": None,
                            "warnings": ["high_missing"],
                        },
                    ],
                }
            ],
        },
        "raw_artifact": {
            "original_filename": "fixture.xlsx",
            "parser_version": "preview-v1",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "file_size_bytes": 1024,
            "file_hash_sha256": "a" * 64,
            "preview_generated_at": "2026-05-05T10:00:00Z",
            "sheet_manifest": [
                {
                    "sheet_index": 1,
                    "sheet_name": "FieldData",
                    "row_count": 5,
                    "max_column_count": 7,
                    "non_empty_cell_count": 25,
                    "detected_block_count": 1,
                }
            ],
            "parse_warning_summary": ["no_blocks_detected:Notes"],
        },
    }

    documents = build_raw_context_documents(upload_detail)

    source_types = {document.source_type for document in documents}
    assert source_types == {"raw_artifact", "sheet_manifest", "parse_warning", "preview_block"}
    block_document = next(document for document in documents if document.source_type == "preview_block")
    assert block_document.upload_session_id == "u1"
    assert block_document.metadata["block_id"] == "S1_B1"
    assert block_document.metadata["canonical_measures"] == ["yield"]
    assert block_document.metadata["warning_codes"] == ["high_missing"]


def test_build_schema_documents_covers_catalog_units_validation_and_query_metadata() -> None:
    query_metadata = {
        "supported_filters": ["upload_session_id", "variable", "location"],
        "supported_group_bys": ["variety", "location"],
        "supported_metrics": ["avg_normalized_value", "count"],
        "supported_validation_statuses": ["valid", "warning", "invalid"],
        "supported_quality_flags": ["missing_unit", "outlier_candidate"],
        "available_variables": ["yield", "moisture"],
        "available_normalized_units": ["kg/ha", "%"],
        "available_varieties": ["Apex"],
        "available_locations": ["north"],
        "available_treatments": ["control"],
        "available_plot_ids": ["P1"],
        "available_validation_statuses": ["valid", "warning"],
        "available_quality_flags": ["outlier_candidate"],
        "aggregations_exclude_invalid_by_default": True,
    }

    documents = build_schema_documents(query_metadata)

    document_ids = {document.document_id for document in documents}
    assert "schema:overview" in document_ids
    assert "query:metadata" in document_ids
    assert "validation:overview" in document_ids
    assert "canonical:measure:yield" in document_ids
    assert "units:yield" in document_ids
    assert "validation:flag:outlier_candidate" in document_ids

    unit_document = next(document for document in documents if document.document_id == "units:yield")
    assert unit_document.source_type == "unit_doc"
    assert unit_document.metadata["canonical_unit"] == "kg/ha"

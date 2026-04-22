from __future__ import annotations

from tests.backend.fake_db import FakeDatabase


def seed_retrieval_upload_context(db: FakeDatabase) -> None:
    db.artifacts["a1"] = {
        "id": "a1",
        "original_filename": "fixture.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file_size_bytes": 2048,
        "file_hash_sha256": "b" * 64,
        "uploaded_at": "2026-05-05T10:00:00Z",
        "parser_version": "preview-v1",
        "storage_type": "db_bytea",
        "storage_path": None,
        "raw_content": b"",
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
        "preview_generated_at": "2026-05-05T10:01:00Z",
        "parse_warning_summary": ["no_blocks_detected:Notes"],
    }
    db.upload_sessions["u1"] = {
        "id": "u1",
        "uploader_user_id": "user-1",
        "status": "committed",
        "original_filename": "fixture.xlsx",
        "artifact_id": "a1",
        "preview_json": {
            "file_name": "fixture.xlsx",
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
                            "suggested": "date",
                            "type_override": None,
                            "semantic_role": "date",
                            "canonical_measure": None,
                            "canonical_dimension": None,
                            "unit": None,
                            "warnings": [],
                        },
                        {
                            "column": "plot_id",
                            "suggested": "text",
                            "type_override": None,
                            "semantic_role": "dimension",
                            "canonical_measure": None,
                            "canonical_dimension": "plot_id",
                            "unit": None,
                            "warnings": [],
                        },
                        {
                            "column": "yield_t/ha",
                            "suggested": "numeric",
                            "type_override": None,
                            "semantic_role": "measure",
                            "canonical_measure": "yield",
                            "canonical_dimension": None,
                            "unit": "t/ha",
                            "warnings": ["high_missing"],
                        },
                    ],
                }
            ],
        },
    }

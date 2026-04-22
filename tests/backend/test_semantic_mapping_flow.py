from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import app
from backend.app.schemas import EditRequest
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import commit_service, preview_service, session_service
from etl.preview_schema import build_preview
from tests.backend.fake_db import FakeDatabase, fake_get_conn


def _build_preview_payload() -> dict[str, object]:
    rows = [
        ["Date", "Plot ID", "Treatment", "Yield", "Moisture", "Notes"],
        ["2025-03-01", "P1", "control", 12.5, 17.2, "north edge"],
        ["2025-03-02", "P2", "fertilized", 13.1, 16.8, "manual check"],
    ]
    block_records = [
        {
            "block_id": "S1_B1",
            "sheet_name": "Field Sheet",
            "row_start": 4,
            "row_end": 6,
            "col_start": 1,
            "col_end": 6,
            "row_count": 3,
            "col_count": 6,
            "rows": rows,
        }
    ]
    return build_preview(file_name="demo.xlsx", block_records=block_records)


def _build_parsed_upload() -> dict[str, object]:
    return {
        "preview": _build_preview_payload(),
        "parser_version": "test_parser_v1",
        "sheet_manifest": [
            {
                "sheet_index": 1,
                "sheet_name": "Field Sheet",
                "row_count": 3,
                "max_column_count": 6,
                "non_empty_cell_count": 18,
                "detected_block_count": 1,
            }
        ],
        "preview_generated_at": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        "parse_warning_summary": [],
    }


def _patch_upload_workflow(monkeypatch: pytest.MonkeyPatch, db: FakeDatabase, parsed_upload: dict[str, object]) -> None:
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(preview_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(commit_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(
        session_service,
        "parse_upload_source",
        lambda file_bytes, filename: deepcopy(parsed_upload),
    )


def test_edit_request_rejects_invalid_dimension_unit_combo() -> None:
    with pytest.raises(ValidationError):
        EditRequest.model_validate(
            {
                "columns": [
                    {
                        "block_id": "S1_B1",
                        "column": "plot_id",
                        "type_override": None,
                        "semantic_role": "dimension",
                        "canonical_measure": None,
                        "canonical_dimension": "plot_id",
                        "unit": "kg/ha",
                    }
                ]
            }
        )


def test_edit_request_rejects_unknown_canonical_measure() -> None:
    with pytest.raises(ValidationError):
        EditRequest.model_validate(
            {
                "columns": [
                    {
                        "block_id": "S1_B1",
                        "column": "yield",
                        "type_override": None,
                        "semantic_role": "measure",
                        "canonical_measure": "protein",
                        "canonical_dimension": None,
                        "unit": "kg/ha",
                    }
                ]
            }
        )


def test_edit_request_rejects_invalid_unit_for_measure() -> None:
    with pytest.raises(ValidationError):
        EditRequest.model_validate(
            {
                "columns": [
                    {
                        "block_id": "S1_B1",
                        "column": "yield",
                        "type_override": None,
                        "semantic_role": "measure",
                        "canonical_measure": "yield",
                        "canonical_dimension": None,
                        "unit": "cm",
                    }
                ]
            }
        )


def test_edit_request_requires_canonical_dimension_for_dimension_role() -> None:
    with pytest.raises(ValidationError):
        EditRequest.model_validate(
            {
                "columns": [
                    {
                        "block_id": "S1_B1",
                        "column": "plot_id",
                        "type_override": None,
                        "semantic_role": "dimension",
                        "canonical_measure": None,
                        "canonical_dimension": None,
                        "unit": None,
                    }
                ]
            }
        )


def test_upload_stores_raw_artifact_metadata_and_detail_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDatabase()
    parsed_upload = _build_parsed_upload()
    _patch_upload_workflow(monkeypatch, db, parsed_upload)

    client = TestClient(app)
    file_bytes = b"raw-excel-content"

    create_response = client.post(
        "/uploads",
        files={"file": ("demo.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert create_response.status_code == 200

    payload = create_response.json()
    upload_id = payload["id"]
    raw_artifact = payload["raw_artifact"]

    assert raw_artifact["original_filename"] == "demo.xlsx"
    assert raw_artifact["mime_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert raw_artifact["file_size_bytes"] == len(file_bytes)
    assert raw_artifact["file_hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    assert raw_artifact["parser_version"] == "test_parser_v1"
    assert raw_artifact["storage_type"] == "db_bytea"
    assert raw_artifact["sheet_manifest"][0]["sheet_name"] == "Field Sheet"

    stored_artifact = db.artifacts[payload["raw_artifact"]["id"]]
    assert stored_artifact["raw_content"] == file_bytes
    assert stored_artifact["file_size_bytes"] == len(file_bytes)
    assert stored_artifact["file_hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()

    detail_response = client.get(f"/uploads/{upload_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "preview_ready"
    assert detail_payload["raw_artifact"]["file_hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    assert detail_payload["preview"]["file_name"] == "demo.xlsx"


def test_preview_edit_and_commit_flow_uses_semantic_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDatabase()
    parsed_upload = _build_parsed_upload()
    _patch_upload_workflow(monkeypatch, db, parsed_upload)

    client = TestClient(app)
    file_bytes = b"fake-bytes"

    create_response = client.post(
        "/uploads",
        files={"file": ("demo.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert create_response.status_code == 200

    upload_id = create_response.json()["id"]
    raw_artifact = create_response.json()["raw_artifact"]
    assert raw_artifact["file_hash_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    assert raw_artifact["sheet_manifest"][0]["detected_block_count"] == 1

    detail_response = client.get(f"/uploads/{upload_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["raw_artifact"]["file_size_bytes"] == len(file_bytes)
    assert detail_response.json()["preview"]["block_count"] == 1

    preview_response = client.get(f"/uploads/{upload_id}/preview")
    assert preview_response.status_code == 200

    preview_json = preview_response.json()["preview"]
    assert preview_response.json()["raw_artifact"]["parser_version"] == "test_parser_v1"
    columns = {item["column"]: item for item in preview_json["blocks"][0]["type_suggestions"]}
    assert columns["date"]["semantic_role"] == "date"
    assert columns["yield"]["semantic_role"] == "measure"
    assert columns["plot_id"]["semantic_role"] == "dimension"
    assert columns["notes"]["semantic_role"] == "ignore"

    edit_payload = {
        "columns": [
            {
                "block_id": "S1_B1",
                "column": "date",
                "type_override": None,
                "semantic_role": "date",
                "canonical_measure": None,
                "canonical_dimension": None,
                "unit": None,
            },
            {
                "block_id": "S1_B1",
                "column": "plot_id",
                "type_override": None,
                "semantic_role": "dimension",
                "canonical_measure": None,
                "canonical_dimension": "plot_id",
                "unit": None,
            },
            {
                "block_id": "S1_B1",
                "column": "treatment",
                "type_override": None,
                "semantic_role": "dimension",
                "canonical_measure": None,
                "canonical_dimension": "treatment",
                "unit": None,
            },
            {
                "block_id": "S1_B1",
                "column": "yield",
                "type_override": None,
                "semantic_role": "measure",
                "canonical_measure": "yield",
                "canonical_dimension": None,
                "unit": "kg/ha",
            },
            {
                "block_id": "S1_B1",
                "column": "moisture",
                "type_override": None,
                "semantic_role": "measure",
                "canonical_measure": "moisture",
                "canonical_dimension": None,
                "unit": "%",
            },
            {
                "block_id": "S1_B1",
                "column": "notes",
                "type_override": None,
                "semantic_role": "ignore",
                "canonical_measure": None,
                "canonical_dimension": None,
                "unit": None,
            },
        ]
    }

    save_response = client.post(f"/uploads/{upload_id}/edits", json=edit_payload)
    assert save_response.status_code == 200

    saved_columns = {
        item["column"]: item
        for item in save_response.json()["preview"]["blocks"][0]["type_suggestions"]
    }
    assert saved_columns["yield"]["canonical_measure"] == "yield"
    assert saved_columns["yield"]["unit"] == "kg/ha"
    assert saved_columns["plot_id"]["canonical_dimension"] == "plot_id"
    assert saved_columns["notes"]["semantic_role"] == "ignore"

    commit_response = client.post(f"/uploads/{upload_id}/commit")
    assert commit_response.status_code == 200
    assert commit_response.json()["staging_rows"] == 4
    assert commit_response.json()["harmonized_rows"] == 4

    observations_response = client.get("/api/harmonized/observations", params={"upload_session_id": upload_id})
    assert observations_response.status_code == 200

    items = observations_response.json()["items"]
    assert len(items) == 4
    assert {item["source_column"] for item in items} == {"yield", "moisture"}
    assert {item["variable"] for item in items} == {"yield", "moisture"}
    assert {item["unit"] for item in items} == {"kg/ha", "%"}
    assert {item["normalized_unit"] for item in items} == {"kg/ha", "%"}
    assert {item["validation_status"] for item in items} == {"valid"}
    assert {item["source_sheet"] for item in items} == {"Field Sheet"}
    assert {item["source_row_index"] for item in items} == {5, 6}
    assert {item["plot_id"] for item in items} == {"P1", "P2"}
    assert {item["treatment"] for item in items} == {"control", "fertilized"}
    assert raw_artifact["id"] in db.artifacts
    assert upload_id in db.upload_sessions
    assert db.upload_sessions[upload_id]["artifact_id"] == raw_artifact["id"]

    first_yield = next(item for item in items if item["source_column"] == "yield" and item["source_row_index"] == 5)
    assert first_yield["observation_date"] == "2025-03-01"
    assert first_yield["plot_id"] == "P1"
    assert first_yield["treatment"] == "control"
    assert first_yield["value"] == 12.5
    assert first_yield["unit"] == "kg/ha"
    assert first_yield["normalized_value"] == 12.5
    assert first_yield["normalized_unit"] == "kg/ha"
    assert first_yield["validation_status"] == "valid"
    assert first_yield["quality_flags"] == []
    stored_first_yield = next(
        row for row in db.harmonized_rows if row["source_column"] == "yield" and row["source_row_index"] == 5
    )
    assert stored_first_yield["dimensions_json"] == {"plot_id": "P1", "treatment": "control"}

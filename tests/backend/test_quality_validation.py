from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import commit_service, preview_service, session_service
from etl.preview_schema import build_preview
from etl.quality_validation import validate_observation_records
from tests.backend.fake_db import FakeDatabase, fake_get_conn


def _build_quality_preview_payload() -> dict[str, object]:
    rows = [
        ["Date", "Plot ID", "Yield", "Moisture", "Notes"],
        ["2025-04-01", "P1", 12.5, 17.2, "ok"],
        ["2025-04-01", "P1", None, 17.9, "duplicate yield"],
        ["bad-date", None, 30.5, None, "outlier and missing context"],
    ]
    block_records = [
        {
            "block_id": "S1_B1",
            "sheet_name": "Quality Sheet",
            "row_start": 3,
            "row_end": 6,
            "col_start": 1,
            "col_end": 5,
            "row_count": 4,
            "col_count": 5,
            "rows": rows,
        }
    ]
    return build_preview(file_name="quality.xlsx", block_records=block_records)


def _build_quality_parsed_upload() -> dict[str, object]:
    return {
        "preview": _build_quality_preview_payload(),
        "parser_version": "test_parser_quality_v1",
        "sheet_manifest": [
            {
                "sheet_index": 1,
                "sheet_name": "Quality Sheet",
                "row_count": 4,
                "max_column_count": 5,
                "non_empty_cell_count": 17,
                "detected_block_count": 1,
            }
        ],
        "preview_generated_at": datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
        "parse_warning_summary": [],
    }


def _patch_upload_workflow(monkeypatch, db: FakeDatabase, parsed_upload: dict[str, object]) -> None:
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(preview_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(commit_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(
        session_service,
        "parse_upload_source",
        lambda file_bytes, filename: deepcopy(parsed_upload),
    )


def test_validate_observation_records_marks_quality_flags() -> None:
    records = [
        {
            "upload_session_id": "u1",
            "source_sheet": "Sheet1",
            "observation_date": "2025-04-01",
            "plot_id": "P1",
            "variety": None,
            "treatment": None,
            "location": None,
            "variable": "yield",
            "value": 12.5,
            "unit": "kg/ha",
            "normalized_value": 12.5,
            "normalized_unit": "kg/ha",
            "_requires_observation_date": True,
        },
        {
            "upload_session_id": "u1",
            "source_sheet": "Sheet1",
            "observation_date": "2025-04-01",
            "plot_id": "P1",
            "variety": None,
            "treatment": None,
            "location": None,
            "variable": "yield",
            "value": None,
            "unit": "kg/ha",
            "normalized_value": None,
            "normalized_unit": None,
            "_requires_observation_date": True,
        },
        {
            "upload_session_id": "u1",
            "source_sheet": "Sheet1",
            "observation_date": None,
            "plot_id": None,
            "variety": None,
            "treatment": None,
            "location": None,
            "variable": "yield",
            "value": 30.5,
            "unit": "t/ha",
            "normalized_value": 30500.0,
            "normalized_unit": "kg/ha",
            "_requires_observation_date": True,
        },
    ]

    validate_observation_records(records)

    assert records[0]["validation_status"] == "warning"
    assert records[0]["quality_flags"] == ["duplicate_candidate"]

    assert records[1]["validation_status"] == "invalid"
    assert "missing_measure_value" in records[1]["quality_flags"]
    assert "missing_unit" in records[1]["quality_flags"]
    assert "duplicate_candidate" in records[1]["quality_flags"]

    assert records[2]["validation_status"] == "invalid"
    assert "missing_required_dimension" in records[2]["quality_flags"]
    assert "missing_observation_date" in records[2]["quality_flags"]
    assert "outlier_candidate" in records[2]["quality_flags"]


def test_commit_and_readback_expose_validation_flags(monkeypatch) -> None:
    db = FakeDatabase()
    parsed_upload = _build_quality_parsed_upload()
    _patch_upload_workflow(monkeypatch, db, parsed_upload)

    client = TestClient(app)
    create_response = client.post(
        "/uploads",
        files={"file": ("quality.xlsx", b"quality-fixture", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert create_response.status_code == 200
    upload_id = create_response.json()["id"]

    save_response = client.post(
        f"/uploads/{upload_id}/edits",
        json={
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
                    "column": "yield",
                    "type_override": None,
                    "semantic_role": "measure",
                    "canonical_measure": "yield",
                    "canonical_dimension": None,
                    "unit": "t/ha",
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
        },
    )
    assert save_response.status_code == 200

    commit_response = client.post(f"/uploads/{upload_id}/commit")
    assert commit_response.status_code == 200
    assert commit_response.json()["staging_rows"] == 6
    assert commit_response.json()["harmonized_rows"] == 6

    all_rows = client.get("/api/harmonized/observations", params={"upload_session_id": upload_id})
    assert all_rows.status_code == 200
    assert all_rows.json()["count"] == 6

    invalid_rows = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "validation_status": "invalid"},
    )
    assert invalid_rows.status_code == 200
    assert invalid_rows.json()["count"] == 3

    duplicate_rows = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "quality_flag": "duplicate_candidate"},
    )
    assert duplicate_rows.status_code == 200
    assert duplicate_rows.json()["count"] == 4

    outlier_rows = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "quality_flag": "outlier_candidate"},
    )
    assert outlier_rows.status_code == 200
    assert outlier_rows.json()["count"] == 1

    outlier_item = outlier_rows.json()["items"][0]
    assert outlier_item["variable"] == "yield"
    assert outlier_item["normalized_value"] == 30500.0
    assert outlier_item["validation_status"] == "invalid"
    assert "missing_observation_date" in outlier_item["quality_flags"]
    assert "missing_required_dimension" in outlier_item["quality_flags"]

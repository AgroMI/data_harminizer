from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from tests.backend.fake_db import FakeDatabase, fake_get_conn


def _seed_harmonized_rows(db: FakeDatabase) -> None:
    db.harmonized_rows = [
        {
            "upload_session_id": "u1",
            "block_id": "S1_B1",
            "source_sheet": "FieldData",
            "source_row_index": 2,
            "source_column": "yield_t/ha",
            "observation_date": date(2026, 5, 1),
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
            "dimensions_json": {"plot_id": "P1", "variety": "Apex", "treatment": "control", "location": "north"},
        },
        {
            "upload_session_id": "u1",
            "block_id": "S1_B1",
            "source_sheet": "FieldData",
            "source_row_index": 3,
            "source_column": "yield_t/ha",
            "observation_date": date(2026, 5, 2),
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
            "dimensions_json": {"plot_id": "P2", "variety": "Apex", "treatment": "treated", "location": "north"},
        },
        {
            "upload_session_id": "u1",
            "block_id": "S1_B1",
            "source_sheet": "FieldData",
            "source_row_index": 4,
            "source_column": "yield_kg_ha",
            "observation_date": date(2026, 5, 3),
            "plot_id": "P3",
            "variety": "Nova",
            "treatment": "control",
            "location": "south",
            "variable": "yield",
            "value": 9000.0,
            "unit": "kg/ha",
            "normalized_value": 9000.0,
            "normalized_unit": "kg/ha",
            "validation_status": "invalid",
            "quality_flags": ["missing_unit"],
            "dimensions_json": {"plot_id": "P3", "variety": "Nova", "treatment": "control", "location": "south"},
        },
        {
            "upload_session_id": "u2",
            "block_id": "S2_B1",
            "source_sheet": "MoistureData",
            "source_row_index": 2,
            "source_column": "moisture_pct",
            "observation_date": date(2026, 5, 1),
            "plot_id": "M1",
            "variety": None,
            "treatment": None,
            "location": "north",
            "variable": "moisture",
            "value": 18.1,
            "unit": "%",
            "normalized_value": 18.1,
            "normalized_unit": "%",
            "validation_status": "valid",
            "quality_flags": [],
            "dimensions_json": {"plot_id": "M1", "location": "north"},
        },
    ]


def test_harmonized_observations_endpoint_filters(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.get(
        "/api/harmonized/observations",
        params={
            "upload_session_id": "u1",
            "variable": "yield",
            "variety": "Apex",
            "plot_id": "P2",
            "observation_date_from": "2026-05-02",
            "observation_date_to": "2026-05-02",
            "validation_status": "warning",
            "quality_flag": "outlier_candidate",
            "normalized_unit": "kg/ha",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["plot_id"] == "P2"
    assert payload["items"][0]["validation_status"] == "warning"
    assert payload["items"][0]["quality_flags"] == ["outlier_candidate"]


def test_harmonized_aggregations_endpoint_supports_avg_and_count(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)

    avg_by_variety = client.get(
        "/api/harmonized/aggregations",
        params={"group_by": "variety", "metric": "avg_normalized_value", "variable": "yield"},
    )
    assert avg_by_variety.status_code == 200
    avg_payload = avg_by_variety.json()
    assert avg_payload["count"] == 1
    assert avg_payload["items"][0]["group_value"] == "Apex"
    assert avg_payload["items"][0]["metric_value"] == 13500.0
    assert avg_payload["items"][0]["record_count"] == 2
    assert avg_payload["items"][0]["normalized_unit"] == "kg/ha"

    avg_by_treatment = client.get(
        "/api/harmonized/aggregations",
        params={"group_by": "treatment", "metric": "avg_normalized_value", "variable": "yield"},
    )
    assert avg_by_treatment.status_code == 200
    treatment_payload = avg_by_treatment.json()
    assert treatment_payload["count"] == 2
    assert {item["group_value"] for item in treatment_payload["items"]} == {"control", "treated"}

    count_by_status = client.get(
        "/api/harmonized/aggregations",
        params={"group_by": "validation_status", "metric": "count"},
    )
    assert count_by_status.status_code == 200
    count_payload = count_by_status.json()
    counts = {item["group_value"]: item["metric_value"] for item in count_payload["items"]}
    assert counts == {"invalid": 1, "valid": 2, "warning": 1}


def test_harmonized_query_metadata_endpoint_reports_supported_and_available_values(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.get("/api/harmonized/query-metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "plot_id" in payload["supported_filters"]
    assert payload["supported_group_bys"] == ["variety", "treatment", "location", "validation_status"]
    assert payload["supported_metrics"] == ["avg_normalized_value", "count"]
    assert payload["available_variables"] == ["moisture", "yield"]
    assert payload["available_normalized_units"] == ["%", "kg/ha"]
    assert payload["available_varieties"] == ["Apex", "Nova"]
    assert payload["available_locations"] == ["north", "south"]
    assert payload["available_treatments"] == ["control", "treated"]
    assert payload["available_plot_ids"] == ["M1", "P1", "P2", "P3"]
    assert payload["available_validation_statuses"] == ["invalid", "valid", "warning"]
    assert payload["available_quality_flags"] == ["missing_unit", "outlier_candidate"]
    assert payload["aggregations_exclude_invalid_by_default"] is True

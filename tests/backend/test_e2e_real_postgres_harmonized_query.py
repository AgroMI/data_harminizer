from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.backend.e2e_real_postgres_helpers import (
    block_by_sheet,
    build_noisy_fixture_edits,
    build_simple_fixture_edits,
    clean_real_database,
    ensure_real_postgres_ready,
    upload_file,
)


@pytest.mark.e2e
def test_e2e_harmonized_query_layer_endpoints() -> None:
    client = TestClient(app)

    simple_upload = upload_file(client, "simple_semantic_fixture.xlsx")
    simple_preview = client.get(f"/uploads/{simple_upload['id']}/preview").json()["preview"]
    simple_block = block_by_sheet(simple_preview, "FieldData")
    assert client.post(
        f"/uploads/{simple_upload['id']}/edits",
        json=build_simple_fixture_edits(simple_block["block_id"]),
    ).status_code == 200
    assert client.post(f"/uploads/{simple_upload['id']}/commit").status_code == 200

    noisy_upload = upload_file(client, "noisy_fixture.xlsx")
    noisy_preview = client.get(f"/uploads/{noisy_upload['id']}/preview").json()["preview"]
    noisy_block = block_by_sheet(noisy_preview, "Measurements")
    assert client.post(
        f"/uploads/{noisy_upload['id']}/edits",
        json=build_noisy_fixture_edits(noisy_block["block_id"]),
    ).status_code == 200
    assert client.post(f"/uploads/{noisy_upload['id']}/commit").status_code == 200

    observations_response = client.get(
        "/api/harmonized/observations",
        params={
            "upload_session_id": noisy_upload["id"],
            "variable": "yield",
            "quality_flag": "duplicate_candidate",
            "limit": 100,
        },
    )
    assert observations_response.status_code == 200
    observation_payload = observations_response.json()
    assert observation_payload["count"] == 2
    assert {item["source_column"] for item in observation_payload["items"]} == {"yield_kg_ha"}
    assert {item["validation_status"] for item in observation_payload["items"]} == {"warning", "invalid"}

    treatment_avg_response = client.get(
        "/api/harmonized/aggregations",
        params={
            "upload_session_id": simple_upload["id"],
            "group_by": "treatment",
            "metric": "avg_normalized_value",
            "variable": "yield",
        },
    )
    assert treatment_avg_response.status_code == 200
    treatment_avg_payload = treatment_avg_response.json()
    treatment_avgs = {item["group_value"]: item["metric_value"] for item in treatment_avg_payload["items"]}
    assert treatment_avgs == {"control": 12700.0, "treated": 21750.0}

    validation_count_response = client.get(
        "/api/harmonized/aggregations",
        params={
            "upload_session_id": noisy_upload["id"],
            "group_by": "validation_status",
            "metric": "count",
        },
    )
    assert validation_count_response.status_code == 200
    validation_counts = {
        item["group_value"]: item["metric_value"] for item in validation_count_response.json()["items"]
    }
    assert validation_counts == {"invalid": 5, "warning": 3}

    metadata_response = client.get("/api/harmonized/query-metadata")
    assert metadata_response.status_code == 200
    metadata_payload = metadata_response.json()
    assert "plot_id" in metadata_payload["supported_filters"]
    assert "yield" in metadata_payload["available_variables"]
    assert "kg/ha" in metadata_payload["available_normalized_units"]
    assert "Apex" in metadata_payload["available_varieties"]
    assert "available_locations" in metadata_payload
    assert "warning" in metadata_payload["available_validation_statuses"]
    assert "duplicate_candidate" in metadata_payload["available_quality_flags"]

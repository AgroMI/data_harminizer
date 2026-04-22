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
def test_e2e_harmonized_nl_query_endpoint() -> None:
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

    treatment_response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Melyik treatment mellett a legnagyobb az atlagos yield?"},
    )
    assert treatment_response.status_code == 200
    treatment_payload = treatment_response.json()
    assert treatment_payload["supported"] is True
    assert treatment_payload["recognized_intent"] == "top_group"
    assert treatment_payload["query_plan"]["group_by"] == "treatment"
    assert treatment_payload["results"]["top_group"]["group_value"] == "treated"
    assert treatment_payload["results"]["top_group"]["metric_value"] == 21750.0

    problematic_response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Mutasd a warning es invalid rekordokat."},
    )
    assert problematic_response.status_code == 200
    problematic_payload = problematic_response.json()
    assert problematic_payload["supported"] is True
    assert problematic_payload["recognized_intent"] == "list_records"
    assert problematic_payload["query_plan"]["filters"]["validation_statuses"] == ["warning", "invalid"]
    assert problematic_payload["results"]["count"] == 9
    assert {item["validation_status"] for item in problematic_payload["results"]["records"]} == {"warning", "invalid"}

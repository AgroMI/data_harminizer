from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.backend.e2e_real_postgres_helpers import (
    block_by_sheet,
    build_multi_sheet_fixture_edits,
    build_noisy_fixture_edits,
    build_simple_fixture_edits,
    clean_real_database,
    ensure_real_postgres_ready,
    harmonized_rows,
    observation_counts,
    upload_file,
    upload_snapshot,
)


@pytest.mark.e2e
def test_e2e_simple_fixture_roundtrip() -> None:
    client = TestClient(app)
    created = upload_file(client, "simple_semantic_fixture.xlsx")
    upload_id = created["id"]

    raw_artifact = created["raw_artifact"]
    assert raw_artifact["sheet_manifest"][0]["sheet_name"] == "FieldData"
    assert raw_artifact["sheet_manifest"][0]["detected_block_count"] == 1

    detail_response = client.get(f"/uploads/{upload_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "preview_ready"
    assert detail["preview"]["block_count"] == 1

    preview_response = client.get(f"/uploads/{upload_id}/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    block = block_by_sheet(preview, "FieldData")
    columns = {item["column"]: item for item in block["type_suggestions"]}

    assert columns["date"]["semantic_role"] == "date"
    assert columns["plot_id"]["semantic_role"] == "dimension"
    assert columns["variety"]["semantic_role"] == "dimension"
    assert columns["treatment"]["semantic_role"] == "dimension"
    assert columns["yield_t/ha"]["semantic_role"] == "measure"
    assert columns["moisture"]["semantic_role"] == "measure"
    assert columns["plant_height_m"]["semantic_role"] == "measure"
    assert columns["notes"]["semantic_role"] == "ignore"
    assert columns["yield_t/ha"]["unit"] == "t/ha"
    assert columns["moisture"]["unit"] == "%"
    assert columns["plant_height_m"]["unit"] == "m"

    save_response = client.post(
        f"/uploads/{upload_id}/edits",
        json=build_simple_fixture_edits(block["block_id"]),
    )
    assert save_response.status_code == 200

    commit_response = client.post(f"/uploads/{upload_id}/commit")
    assert commit_response.status_code == 200
    assert commit_response.json()["staging_rows"] == 12
    assert commit_response.json()["harmonized_rows"] == 12

    observations_response = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "limit": 100},
    )
    assert observations_response.status_code == 200
    items = observations_response.json()["items"]
    assert len(items) == 12
    assert {item["variable"] for item in items} == {"yield", "moisture", "plant_height"}
    assert {item["unit"] for item in items} == {"t/ha", "%", "m"}
    assert {item["normalized_unit"] for item in items} == {"kg/ha", "%", "cm"}
    assert {item["validation_status"] for item in items} == {"valid", "warning"}
    assert {item["source_sheet"] for item in items} == {"FieldData"}
    assert {item["source_row_index"] for item in items} == {2, 3, 4, 5}
    assert {item["variety"] for item in items} == {"Apex", "Nova"}
    assert {item["plot_id"] for item in items} == {"P1", "P2", "P3", "P4"}

    first_yield = next(item for item in items if item["source_column"] == "yield_t/ha" and item["source_row_index"] == 2)
    assert first_yield["observation_date"] == "2026-05-01"
    assert first_yield["plot_id"] == "P1"
    assert first_yield["variety"] == "Apex"
    assert first_yield["treatment"] == "control"
    assert first_yield["value"] == 12.5
    assert first_yield["unit"] == "t/ha"
    assert first_yield["normalized_value"] == 12500.0
    assert first_yield["normalized_unit"] == "kg/ha"

    first_height = next(
        item for item in items if item["source_column"] == "plant_height_m" and item["source_row_index"] == 2
    )
    assert first_height["value"] == 1.12
    assert first_height["unit"] == "m"
    assert first_height["normalized_value"] == 112.0
    assert first_height["normalized_unit"] == "cm"
    assert first_height["validation_status"] == "valid"
    assert first_height["quality_flags"] == []

    outlier_yield = next(
        item for item in items if item["source_column"] == "yield_t/ha" and item["source_row_index"] == 5
    )
    assert outlier_yield["value"] == 30.4
    assert outlier_yield["normalized_value"] == 30400.0
    assert outlier_yield["validation_status"] == "warning"
    assert outlier_yield["quality_flags"] == ["outlier_candidate"]

    filtered_response = client.get(
        "/api/harmonized/observations",
        params={
            "upload_session_id": upload_id,
            "variable": "yield",
            "variety": "Apex",
            "normalized_unit": "kg/ha",
            "limit": 100,
        },
    )
    assert filtered_response.status_code == 200
    filtered_items = filtered_response.json()["items"]
    assert len(filtered_items) == 2
    assert all(item["variable"] == "yield" for item in filtered_items)
    assert all(item["variety"] == "Apex" for item in filtered_items)
    assert all(item["normalized_unit"] == "kg/ha" for item in filtered_items)

    stored_rows = harmonized_rows(upload_id=upload_id)
    stored_first_yield = next(
        item for item in stored_rows if item["source_column"] == "yield_t/ha" and item["source_row_index"] == 2
    )
    assert stored_first_yield["dimensions_json"] == {"plot_id": "P1", "variety": "Apex", "treatment": "control"}

    snapshot = upload_snapshot(upload_id)
    assert snapshot["artifact_id"] is not None
    assert snapshot["raw_content_size"] == raw_artifact["file_size_bytes"]
    assert snapshot["file_hash_sha256"] == raw_artifact["file_hash_sha256"]
    assert snapshot["preview_json"]["block_count"] == 1
    counts = observation_counts(upload_id)
    assert counts == {"staging": 12, "harmonized": 12}


@pytest.mark.e2e
def test_e2e_multi_sheet_fixture_roundtrip() -> None:
    client = TestClient(app)
    created = upload_file(client, "multi_sheet_fixture.xlsx")
    upload_id = created["id"]

    assert len(created["raw_artifact"]["sheet_manifest"]) == 2

    preview_response = client.get(f"/uploads/{upload_id}/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    assert preview["block_count"] == 2

    yield_block = block_by_sheet(preview, "Yield2026")
    moisture_block = block_by_sheet(preview, "Moisture2026")

    save_response = client.post(
        f"/uploads/{upload_id}/edits",
        json=build_multi_sheet_fixture_edits(yield_block["block_id"], moisture_block["block_id"]),
    )
    assert save_response.status_code == 200

    commit_response = client.post(f"/uploads/{upload_id}/commit")
    assert commit_response.status_code == 200
    assert commit_response.json()["staging_rows"] == 8
    assert commit_response.json()["harmonized_rows"] == 8

    observations_response = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "limit": 100},
    )
    assert observations_response.status_code == 200
    items = observations_response.json()["items"]
    assert len(items) == 8
    assert {item["source_sheet"] for item in items} == {"Yield2026", "Moisture2026"}
    assert {item["variable"] for item in items} == {"yield", "moisture"}
    assert {item["unit"] for item in items} == {"kg/ha", "%"}
    assert {item["normalized_unit"] for item in items} == {"kg/ha", "%"}
    assert {item["validation_status"] for item in items} == {"valid"}
    assert any(item["normalized_value"] == item["value"] for item in items if item["variable"] == "yield")
    assert any(item["variety"] == "Apex" and item["variable"] == "yield" for item in items)
    assert any(item["location"] == "north" and item["variable"] == "moisture" for item in items)

    stored_rows = harmonized_rows(upload_id=upload_id)
    assert any(
        item["dimensions_json"] == {"plot_id": "Y1", "variety": "Apex", "treatment": "control"}
        for item in stored_rows
    )
    assert any(item["dimensions_json"] == {"plot_id": "M1", "location": "north"} for item in stored_rows)

    snapshot = upload_snapshot(upload_id)
    assert len(snapshot["sheet_manifest"]) == 2
    assert snapshot["preview_json"]["block_count"] == 2
    counts = observation_counts(upload_id)
    assert counts == {"staging": 8, "harmonized": 8}


@pytest.mark.e2e
def test_e2e_noisy_fixture_roundtrip() -> None:
    client = TestClient(app)
    created = upload_file(client, "noisy_fixture.xlsx")
    upload_id = created["id"]

    raw_artifact = created["raw_artifact"]
    assert "no_blocks_detected:Notes" in raw_artifact["parse_warning_summary"]
    assert len(raw_artifact["sheet_manifest"]) == 2

    preview_response = client.get(f"/uploads/{upload_id}/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    assert preview["block_count"] == 1

    block = block_by_sheet(preview, "Measurements")
    assert block["headers"] == ["date", "plot_id", "yield_kg_ha", "moisture_pct", "notes"]
    columns = {item["column"]: item for item in block["type_suggestions"]}
    assert "high_missing" in columns["yield_kg_ha"]["warnings"]
    assert columns["yield_kg_ha"]["semantic_role"] == "measure"
    assert columns["moisture_pct"]["semantic_role"] == "measure"
    assert columns["yield_kg_ha"]["unit"] == "kg/ha"
    assert columns["moisture_pct"]["unit"] == "%"

    save_response = client.post(
        f"/uploads/{upload_id}/edits",
        json=build_noisy_fixture_edits(block["block_id"]),
    )
    assert save_response.status_code == 200

    commit_response = client.post(f"/uploads/{upload_id}/commit")
    assert commit_response.status_code == 200
    assert commit_response.json()["staging_rows"] == 8
    assert commit_response.json()["harmonized_rows"] == 8

    observations_response = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "limit": 100},
    )
    assert observations_response.status_code == 200
    items = observations_response.json()["items"]
    assert len(items) == 8
    assert {item["source_sheet"] for item in items} == {"Measurements"}
    assert {item["variable"] for item in items} == {"yield", "moisture"}
    assert {item["normalized_unit"] for item in items} == {"kg/ha", "%", None}
    assert {item["source_row_index"] for item in items} == {4, 5, 6, 7}
    assert any(item["source_column"] == "yield_kg_ha" and item["source_row_index"] == 4 for item in items)
    assert any(item["source_column"] == "moisture_pct" and item["source_row_index"] == 7 for item in items)
    assert any(
        item["plot_id"] == "P10" and item["quality_flags"] == ["duplicate_candidate"]
        for item in items
        if item["source_column"] == "moisture_pct" and item["source_row_index"] == 4
    )

    duplicate_rows = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "quality_flag": "duplicate_candidate", "limit": 100},
    )
    assert duplicate_rows.status_code == 200
    assert duplicate_rows.json()["count"] == 4

    invalid_rows = client.get(
        "/api/harmonized/observations",
        params={"upload_session_id": upload_id, "validation_status": "invalid", "limit": 100},
    )
    assert invalid_rows.status_code == 200
    assert invalid_rows.json()["count"] == 5

    missing_yield = next(
        item for item in items if item["source_column"] == "yield_kg_ha" and item["source_row_index"] == 5
    )
    assert missing_yield["value"] is None
    assert missing_yield["normalized_value"] is None
    assert missing_yield["validation_status"] == "invalid"
    assert "missing_measure_value" in missing_yield["quality_flags"]
    assert "duplicate_candidate" in missing_yield["quality_flags"]

    missing_dimension = next(
        item for item in items if item["source_row_index"] == 6 and item["source_column"] == "yield_kg_ha"
    )
    assert missing_dimension["plot_id"] is None
    assert "missing_required_dimension" in missing_dimension["quality_flags"]

    missing_date = next(
        item for item in items if item["source_row_index"] == 7 and item["source_column"] == "moisture_pct"
    )
    assert missing_date["observation_date"] is None
    assert "missing_observation_date" in missing_date["quality_flags"]

    snapshot = upload_snapshot(upload_id)
    assert snapshot["parse_warning_summary"] == raw_artifact["parse_warning_summary"]
    assert snapshot["preview_json"]["block_count"] == 1
    counts = observation_counts(upload_id)
    assert counts == {"staging": 8, "harmonized": 8}


@pytest.mark.e2e
def test_e2e_different_workbooks_converge_to_same_canonical_measure() -> None:
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

    yield_response = client.get(
        "/api/harmonized/observations",
        params={"variable": "yield", "normalized_unit": "kg/ha", "limit": 100},
    )
    assert yield_response.status_code == 200
    yield_items = yield_response.json()["items"]

    assert len(yield_items) == 6
    assert {item["source_column"] for item in yield_items} == {"yield_t/ha", "yield_kg_ha"}
    assert {item["variable"] for item in yield_items} == {"yield"}
    assert {item["normalized_unit"] for item in yield_items} == {"kg/ha"}
    assert any(
        item["unit"] == "t/ha" and item["normalized_value"] == item["value"] * 1000.0
        for item in yield_items
    )
    assert any(item["unit"] == "kg/ha" and item["normalized_value"] == item["value"] for item in yield_items)
    assert {item["upload_session_id"] for item in yield_items} == {simple_upload["id"], noisy_upload["id"]}

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.backend.e2e_real_postgres_helpers import (
    block_by_sheet,
    build_simple_fixture_edits,
    clean_real_database,
    ensure_real_postgres_ready,
    upload_file,
)


@pytest.mark.e2e
def test_e2e_rag_answer_endpoint_returns_answer_bundle() -> None:
    client = TestClient(app)

    created = upload_file(client, "simple_semantic_fixture.xlsx")
    upload_id = created["id"]

    preview = client.get(f"/uploads/{upload_id}/preview").json()["preview"]
    block = block_by_sheet(preview, "FieldData")
    assert client.post(
        f"/uploads/{upload_id}/edits",
        json=build_simple_fixture_edits(block["block_id"]),
    ).status_code == 200
    assert client.post(f"/uploads/{upload_id}/commit").status_code == 200

    response = client.post(
        "/api/rag/answer",
        json={
            "question": "Mi az atlagos yield fajtankent?",
            "upload_session_id": upload_id,
            "include_context": True,
            "include_schema_context": True,
            "include_raw_context": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is True
    assert payload["recognized_intent"] == "aggregate"
    assert payload["result_type"] == "aggregation"
    assert payload["results"]["count"] == 2
    assert payload["answer_summary"]
    assert any(item["section_type"] == "result_overview" for item in payload["answer_sections"])
    assert any(item["section_type"] == "source_context" for item in payload["answer_sections"])
    assert any(item["finding_id"] == "highest_group" for item in payload["key_findings"])
    assert any(item["note_id"] == "aggregation_scope" for item in payload["quality_notes"])
    assert any(item["source_type"] == "query_result" for item in payload["sources"])
    assert any(item["source_id"] == "query:result" for item in payload["sources"])
    assert any(item["source_type"] == "raw_artifact" for item in payload["sources"])
    assert any(item["upload_session_id"] == upload_id for item in payload["context_documents"])

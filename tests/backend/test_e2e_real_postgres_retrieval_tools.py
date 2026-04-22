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
def test_e2e_retrieval_context_endpoints() -> None:
    client = TestClient(app)

    created = upload_file(client, "noisy_fixture.xlsx")
    upload_id = created["id"]

    preview = client.get(f"/uploads/{upload_id}/preview").json()["preview"]
    block = block_by_sheet(preview, "Measurements")
    assert client.post(
        f"/uploads/{upload_id}/edits",
        json=build_noisy_fixture_edits(block["block_id"]),
    ).status_code == 200
    assert client.post(f"/uploads/{upload_id}/commit").status_code == 200

    context_response = client.get(
        "/api/retrieval/context",
        params={
            "upload_session_id": upload_id,
            "variable": "yield",
            "question": "Show yield issues and provenance context.",
            "include_schema_context": "true",
            "include_raw_context": "true",
        },
    )
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["summary"]
    assert context_payload["query_metadata_snapshot"]["available_variables"] == ["moisture", "yield"]
    context_source_types = {item["source_type"] for item in context_payload["context_documents"]}
    assert "raw_artifact" in context_source_types
    assert "preview_block" in context_source_types
    assert "validation_doc" in context_source_types
    assert any(item["upload_session_id"] == upload_id for item in context_payload["context_documents"])

    search_response = client.post(
        "/api/retrieval/search",
        json={
            "query": "no_blocks_detected Notes",
            "upload_session_id": upload_id,
            "limit": 5,
        },
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["count"] >= 1
    assert any(item["source_type"] == "parse_warning" for item in search_payload["items"])


@pytest.mark.e2e
def test_e2e_tool_endpoints() -> None:
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

    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200
    tools_payload = tools_response.json()
    assert {item["tool_name"] for item in tools_payload["tools"]} == {
        "metadata_tool",
        "query_tool",
        "retrieval_tool",
        "unit_conversion_tool",
    }

    query_tool_response = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "query_tool",
            "arguments": {
                "operation": "aggregate",
                "filters": {
                    "upload_session_id": upload_id,
                    "variable": "yield",
                },
                "group_by": "variety",
                "metric": "avg_normalized_value",
            },
        },
    )
    assert query_tool_response.status_code == 200
    query_tool_payload = query_tool_response.json()
    assert query_tool_payload["success"] is True
    assert {item["group_value"] for item in query_tool_payload["result"]["items"]} == {"Apex", "Nova"}

    retrieval_tool_response = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "retrieval_tool",
            "arguments": {
                "operation": "context",
                "upload_session_id": upload_id,
                "variable": "yield",
                "question": "Show yield provenance context.",
                "include_schema_context": True,
                "include_raw_context": True,
            },
        },
    )
    assert retrieval_tool_response.status_code == 200
    retrieval_tool_payload = retrieval_tool_response.json()
    assert retrieval_tool_payload["success"] is True
    assert any(
        item["source_type"] == "raw_artifact"
        for item in retrieval_tool_payload["result"]["context_documents"]
    )

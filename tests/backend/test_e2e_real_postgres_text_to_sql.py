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
def test_e2e_mcp_and_text_to_sql_pipeline() -> None:
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

    tools_response = client.get("/api/mcp/tools")
    assert tools_response.status_code == 200
    assert {item["tool_name"] for item in tools_response.json()["tools"]} >= {
        "describe_schema",
        "plan_query",
        "generate_sql",
        "validate_sql",
        "execute_sql",
    }

    pipeline_response = client.post(
        "/api/text-to-sql/query",
        json={"question": "Average yield by variety", "upload_session_id": upload_id},
        headers={"X-Correlation-Id": "real-pipeline"},
    )
    assert pipeline_response.status_code == 200
    payload = pipeline_response.json()
    assert payload["status"] == "supported"
    assert payload["validation"]["valid"] is True
    assert payload["execution"]["row_count"] >= 1
    assert any(item["group_value"] == "Apex" for item in payload["answer"]["items"])

    audit_response = client.get("/api/mcp/audit", params={"correlation_id": "real-pipeline"})
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["count"] == 4
    assert {item["tool_name"] for item in audit_payload["items"]} == {
        "plan_query",
        "generate_sql",
        "validate_sql",
        "execute_sql",
    }

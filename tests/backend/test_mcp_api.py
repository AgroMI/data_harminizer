from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.mcp import audit as mcp_audit
from backend.app.mcp.tools import core_tools
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from backend.app.text_to_sql import planner, sql_executor
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def _patch_dependencies(monkeypatch, db: FakeDatabase) -> None:
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(mcp_audit, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(sql_executor, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(planner, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)
    monkeypatch.setattr(core_tools, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)


def test_mcp_tool_discovery_lists_expected_tools(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.get("/api/mcp/tools")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 7
    assert {item["tool_name"] for item in payload["tools"]} == {
        "describe_schema",
        "plan_query",
        "generate_sql",
        "validate_sql",
        "execute_sql",
        "explain_metadata",
        "retrieve_evidence",
    }


def test_mcp_tool_chain_plans_generates_and_validates(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)

    client = TestClient(app)

    plan_response = client.post(
        "/api/mcp/invoke",
        json={"tool_name": "plan_query", "arguments": {"question": "Average yield by treatment"}},
        headers={"X-Correlation-Id": "corr-chain"},
    )
    assert plan_response.status_code == 200
    plan_payload = plan_response.json()
    assert plan_payload["success"] is True
    assert plan_payload["result"]["query_plan"]["grouping"] == ["treatment"]

    sql_response = client.post(
        "/api/mcp/invoke",
        json={"tool_name": "generate_sql", "arguments": {"query_plan": plan_payload["result"]["query_plan"]}},
        headers={"X-Correlation-Id": "corr-chain"},
    )
    assert sql_response.status_code == 200
    sql_payload = sql_response.json()
    assert sql_payload["success"] is True
    assert "FROM safe.harmonized_observations_v1" in sql_payload["result"]["sql"]

    validation_response = client.post(
        "/api/mcp/invoke",
        json={
            "tool_name": "validate_sql",
            "arguments": {
                "sql": sql_payload["result"]["sql"],
                "parameters": sql_payload["result"]["parameters"],
                "query_plan": plan_payload["result"]["query_plan"],
            },
        },
        headers={"X-Correlation-Id": "corr-chain"},
    )
    assert validation_response.status_code == 200
    validation_payload = validation_response.json()
    assert validation_payload["success"] is True
    assert validation_payload["result"]["validation"]["valid"] is True


def test_mcp_execute_sql_rejects_unsafe_statement(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/mcp/invoke",
        json={
            "tool_name": "execute_sql",
            "arguments": {
                "sql": "SELECT * FROM harmonized.observations LIMIT %s",
                "parameters": [10],
                "query_plan": {
                    "status": "supported",
                    "intent": "select_records",
                    "source_relation": "safe.harmonized_observations_v1",
                    "selected_measures": [],
                    "selected_dimensions": [],
                    "filters": [],
                    "aggregations": [],
                    "grouping": [],
                    "ordering": [],
                    "limit": 10,
                    "unit_handling": {"mode": "none", "normalized_unit": None, "note": None},
                    "ambiguity_flags": [],
                    "validation_notes": [],
                    "trace": [],
                    "target_measure": None,
                    "result_type": "records"
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "sql_validation_failed"

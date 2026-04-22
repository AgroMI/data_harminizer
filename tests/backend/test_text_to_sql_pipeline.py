from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.main import app
from backend.app.mcp import audit as mcp_audit
from backend.app.mcp.tools import core_tools
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from backend.app.text_to_sql import planner, sql_executor
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def _patch_text_to_sql_dependencies(monkeypatch, db: FakeDatabase) -> None:
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(mcp_audit, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(sql_executor, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(planner, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)
    monkeypatch.setattr(core_tools, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)


def test_text_to_sql_pipeline_endpoint_returns_aggregation_and_audit(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_text_to_sql_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "What is the average yield by variety?"},
        headers={"X-Correlation-Id": "corr-avg-variety"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["correlation_id"] == "corr-avg-variety"
    assert payload["status"] == "supported"
    assert payload["result_type"] == "aggregation"
    assert payload["query_plan"]["intent"] == "aggregate"
    assert payload["query_plan"]["grouping"] == ["variety"]
    assert payload["planning_metadata"]["requested_mode"] == "deterministic"
    assert payload["planning_metadata"]["plan_origin"] == "deterministic"
    assert payload["planning_metadata"]["llm_used"] is False
    assert payload["validation"]["valid"] is True
    assert payload["execution"]["row_count"] == 1
    assert payload["answer"]["items"][0]["group_value"] == "Apex"
    assert payload["tool_trace"][-1]["tool_name"] == "execute_sql"

    audit_response = client.get("/api/mcp/audit", params={"correlation_id": "corr-avg-variety"})
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["count"] == 4
    assert [item["tool_name"] for item in audit_payload["items"]] == [
        "execute_sql",
        "validate_sql",
        "generate_sql",
        "plan_query",
    ]


def test_text_to_sql_pipeline_rejects_unsafe_request_without_execution(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_text_to_sql_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "SELECT * FROM harmonized.observations"},
        headers={"X-Correlation-Id": "corr-unsafe"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["result_type"] == "unsupported"
    assert payload["planning_metadata"]["plan_origin"] == "deterministic"
    assert payload["generated_sql"] is None
    assert payload["execution"] is None

    audit_response = client.get("/api/mcp/audit", params={"correlation_id": "corr-unsafe"})
    assert audit_response.status_code == 200
    audit_payload = audit_response.json()
    assert audit_payload["count"] == 1
    assert audit_payload["items"][0]["tool_name"] == "plan_query"


def test_text_to_sql_deterministic_mode_does_not_special_case_hungarian_keywords(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_text_to_sql_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "Mi az atlagos yield fajtankent?"},
        headers={"X-Correlation-Id": "corr-hu-deterministic"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["planning_metadata"]["requested_mode"] == "deterministic"
    assert payload["planning_metadata"]["plan_origin"] == "deterministic"
    assert payload["generated_sql"] is None


def test_text_to_sql_benchmark_endpoint_returns_summary(monkeypatch) -> None:
    class FakeReport:
        def to_dict(self) -> dict[str, object]:
            return {
                "dataset_name": "demo",
                "total_questions": 1,
                "query_plan_correctness": {"correct": 1, "total": 1, "accuracy": 1.0},
                "sql_validity_rate": {"correct": 1, "total": 1, "accuracy": 1.0},
                "execution_success_rate": {"correct": 1, "total": 1, "accuracy": 1.0},
                "answer_correctness": {"correct": 1, "total": 1, "accuracy": 1.0},
                "unsupported_query_rate": {"correct": 0, "total": 0, "accuracy": 0.0},
                "rejected_unsafe_query_rate": {"correct": 0, "total": 0, "accuracy": 0.0},
                "questions": [],
            }

    monkeypatch.setattr(main, "run_text_to_sql_benchmark", lambda: FakeReport())

    client = TestClient(app)
    response = client.get("/api/text-to-sql/benchmark")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_name"] == "demo"
    assert payload["total_questions"] == 1
    assert payload["query_plan_correctness"]["accuracy"] == 1.0

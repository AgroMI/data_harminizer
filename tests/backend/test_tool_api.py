from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from backend.app.tools.tool_registry import default_tool_registry
from backend.app.tools.tool_runner import execute_tool
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.retrieval_test_helpers import seed_retrieval_upload_context
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def _patch_tool_dependencies(monkeypatch, db: FakeDatabase) -> None:
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))


def test_tool_runner_rejects_invalid_tool_name() -> None:
    response = execute_tool(
        tool_name="unknown_tool",
        arguments={},
        registry=default_tool_registry(),
    )

    assert response["success"] is False
    assert response["error"]["code"] == "invalid_tool_name"
    assert response["tool_name"] == "unknown_tool"


def test_tool_runner_rejects_invalid_arguments() -> None:
    response = execute_tool(
        tool_name="unit_conversion_tool",
        arguments={"canonical_measure": "yield", "source_unit": "t/ha"},
        registry=default_tool_registry(),
    )

    assert response["success"] is False
    assert response["error"]["code"] == "invalid_arguments"


def test_query_tool_executes_aggregate_operation(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_tool_dependencies(monkeypatch, db)

    response = execute_tool(
        tool_name="query_tool",
        arguments={
            "operation": "aggregate",
            "filters": {"variable": "yield"},
            "group_by": "treatment",
            "metric": "avg_normalized_value",
        },
        registry=default_tool_registry(),
    )

    assert response["success"] is True
    items = response["result"]["items"]
    assert {item["group_value"] for item in items} == {"control", "treated"}


def test_metadata_tool_returns_catalog_and_query_metadata(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_tool_dependencies(monkeypatch, db)

    response = execute_tool(
        tool_name="metadata_tool",
        arguments={"include_query_metadata": True},
        registry=default_tool_registry(),
    )

    assert response["success"] is True
    assert response["result"]["canonical_variables"] == ["yield", "moisture", "plant_height"]
    assert response["result"]["query_metadata"]["available_variables"] == ["moisture", "yield"]


def test_unit_conversion_tool_returns_normalized_value() -> None:
    response = execute_tool(
        tool_name="unit_conversion_tool",
        arguments={
            "canonical_measure": "yield",
            "source_unit": "t/ha",
            "value": 12.5,
        },
        registry=default_tool_registry(),
    )

    assert response["success"] is True
    assert response["result"]["normalized_value"] == 12500.0
    assert response["result"]["normalized_unit"] == "kg/ha"


def test_retrieval_tool_returns_search_results(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    _patch_tool_dependencies(monkeypatch, db)

    response = execute_tool(
        tool_name="retrieval_tool",
        arguments={
            "operation": "search",
            "query": "yield unit kg/ha",
            "upload_session_id": "u1",
        },
        registry=default_tool_registry(),
    )

    assert response["success"] is True
    assert response["result"]["count"] >= 1
    assert response["result"]["items"][0]["source_type"] in {
        "unit_doc",
        "canonical_catalog",
        "preview_block",
        "query_metadata",
    }


def test_tool_runner_returns_unified_response_envelope(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_tool_dependencies(monkeypatch, db)

    response = execute_tool(
        tool_name="metadata_tool",
        arguments={"include_query_metadata": False},
        registry=default_tool_registry(),
    )

    assert response["tool_name"] == "metadata_tool"
    assert response["success"] is True
    assert response["error"] is None
    assert response["metadata"] == {"category": "metadata", "read_only": True}


def test_tool_api_endpoints_support_discovery_and_execution(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_tool_dependencies(monkeypatch, db)

    client = TestClient(app)

    list_response = client.get("/api/tools")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["count"] == 4
    assert {item["tool_name"] for item in list_payload["tools"]} == {
        "metadata_tool",
        "query_tool",
        "retrieval_tool",
        "unit_conversion_tool",
    }

    execute_response = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "unit_conversion_tool",
            "arguments": {
                "canonical_measure": "yield",
                "source_unit": "t/ha",
                "value": 10.0,
            },
        },
    )
    assert execute_response.status_code == 200
    payload = execute_response.json()
    assert payload["success"] is True
    assert payload["result"]["normalized_value"] == 10000.0


def test_tool_api_returns_error_for_invalid_arguments() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "unit_conversion_tool",
            "arguments": {
                "canonical_measure": "yield",
                "source_unit": "unsupported",
                "value": 10.0,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "invalid_arguments"

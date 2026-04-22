from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.retrieval_test_helpers import seed_retrieval_upload_context
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def test_retrieval_context_endpoint_returns_schema_and_raw_context(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.get(
        "/api/retrieval/context",
        params={
            "upload_session_id": "u1",
            "variable": "yield",
            "question": "What is the average yield by variety?",
            "include_schema_context": "true",
            "include_raw_context": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]
    assert payload["query_metadata_snapshot"]["available_variables"] == ["moisture", "yield"]
    assert len(payload["context_documents"]) >= 4
    source_types = {item["source_type"] for item in payload["context_documents"]}
    assert "raw_artifact" in source_types
    assert "preview_block" in source_types
    assert "canonical_catalog" in source_types
    assert "unit_doc" in source_types


def test_retrieval_search_endpoint_returns_ranked_structured_hits(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.post(
        "/api/retrieval/search",
        json={
            "query": "yield kg/ha unit",
            "upload_session_id": "u1",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    first_hit = payload["items"][0]
    assert first_hit["source_type"] in {"unit_doc", "canonical_catalog", "preview_block", "query_metadata"}
    assert isinstance(first_hit["snippet"], str) and first_hit["snippet"]
    assert "metadata" in first_hit
    assert "title" in first_hit


def test_retrieval_context_endpoint_keeps_source_typing_and_metadata(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.get(
        "/api/retrieval/context",
        params={
            "upload_session_id": "u1",
            "include_schema_context": "false",
            "include_raw_context": "true",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_metadata_snapshot"] is None
    raw_artifact_doc = next(item for item in payload["context_documents"] if item["source_type"] == "raw_artifact")
    assert raw_artifact_doc["upload_session_id"] == "u1"
    assert raw_artifact_doc["metadata"]["original_filename"] == "fixture.xlsx"
    assert any(item["source_type"] == "sheet_manifest" for item in payload["context_documents"])
    assert any(item["source_type"] == "parse_warning" for item in payload["context_documents"])

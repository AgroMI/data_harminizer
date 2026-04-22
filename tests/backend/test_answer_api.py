from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.retrieval_test_helpers import seed_retrieval_upload_context
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def _configure_answer_dependencies(monkeypatch, db: FakeDatabase) -> None:
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))


def test_answer_endpoint_builds_supported_aggregate_bundle(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    _configure_answer_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/rag/answer",
        json={
            "question": "Mi az atlagos yield fajtankent?",
            "upload_session_id": "u1",
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
    assert payload["query_plan"]["filters"]["upload_session_id"] == "u1"
    assert payload["answer_summary"].startswith("The query returned 1 variety groups for average normalized yield.")
    assert payload["query_metadata_snapshot"]["available_variables"] == ["moisture", "yield"]
    assert payload["key_findings"][0]["finding_id"] == "aggregation_group_count"
    assert payload["key_findings"][0]["evidence_source_ids"] == ["query:result"]
    assert any(item["section_type"] == "result_overview" for item in payload["answer_sections"])
    source_context = next(item for item in payload["answer_sections"] if item["section_type"] == "source_context")
    assert "upload_session_id=u1" in source_context["body"]
    assert any(note["note_id"] == "aggregation_scope" for note in payload["quality_notes"])
    assert any(item["source_type"] == "query_result" for item in payload["sources"])
    assert any(item["source_type"] == "raw_artifact" for item in payload["sources"])
    assert any(item["source_type"] == "parse_warning" for item in payload["sources"])
    assert any(item["source_type"] == "canonical_catalog" for item in payload["sources"])
    assert all(item["source_id"] for item in payload["sources"])


def test_answer_endpoint_builds_record_summary_and_sources(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    _configure_answer_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/rag/answer",
        json={
            "question": "Mutasd a warning es invalid rekordokat.",
            "upload_session_id": "u1",
            "include_context": True,
            "include_schema_context": True,
            "include_raw_context": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is True
    assert payload["result_type"] == "records"
    assert payload["results"]["count"] == 2
    assert payload["answer_summary"].startswith("The query returned 2 harmonized records.")
    assert any(finding["finding_id"] == "status_mix" for finding in payload["key_findings"])
    assert any(note["note_id"] == "validation_status" for note in payload["quality_notes"])
    assert any(note["note_id"] == "quality_flags" for note in payload["quality_notes"])
    quality_section = next(item for item in payload["answer_sections"] if item["section_type"] == "quality_context")
    assert quality_section["source_ids"]
    assert payload["sources"][0]["source_id"]
    assert payload["sources"][0]["document_id"]
    assert payload["sources"][0]["title"]
    assert "snippet" in payload["sources"][0]


def test_answer_endpoint_supports_direct_scope_answer_without_question(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    _configure_answer_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/rag/answer",
        json={
            "upload_session_id": "u1",
            "variable": "yield",
            "include_context": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "Direct answer scope: variable=yield, upload_session_id=u1"
    assert payload["supported"] is True
    assert payload["recognized_intent"] == "list_records"
    assert payload["result_type"] == "records"
    assert payload["query_plan"]["filters"]["upload_session_id"] == "u1"
    assert payload["query_plan"]["filters"]["variable"] == "yield"
    assert payload["results"]["count"] == 3
    assert payload["context_documents"] == []
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["source_type"] == "query_result"
    assert any(item["section_type"] == "limitations" for item in payload["answer_sections"])


def test_answer_endpoint_handles_unsupported_questions_cleanly(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    seed_retrieval_upload_context(db)
    _configure_answer_dependencies(monkeypatch, db)

    client = TestClient(app)
    response = client.post(
        "/api/rag/answer",
        json={
            "question": "Rajzolj diagramot a teljes trendrol.",
            "upload_session_id": "u1",
            "variable": "yield",
            "include_context": True,
            "include_schema_context": True,
            "include_raw_context": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is False
    assert payload["result_type"] == "unsupported"
    assert payload["results"]["count"] == 0
    assert payload["answer_summary"].startswith(
        "The request is outside the supported read-only query patterns"
    )
    assert payload["key_findings"][0]["finding_id"] == "support_status"
    assert any(item["section_type"] == "limitations" for item in payload["answer_sections"])
    assert len(payload["context_documents"]) >= 1
    assert any(item["source_type"] == "raw_artifact" for item in payload["sources"])

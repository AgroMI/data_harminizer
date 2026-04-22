from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import harmonized_query_service
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def test_nl_query_recognizes_average_yield_by_variety(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Mi az atlagos yield fajtankent?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is True
    assert payload["recognized_intent"] == "aggregate"
    assert payload["query_plan"]["intent_type"] == "aggregate"
    assert payload["query_plan"]["group_by"] == "variety"
    assert payload["query_plan"]["variable"] == "yield"
    assert payload["query_plan"]["metric"] == "avg_normalized_value"
    assert payload["query_plan"]["filters"]["normalized_unit"] == "kg/ha"
    assert payload["result_type"] == "aggregation"
    assert payload["results"]["count"] == 1
    assert payload["results"]["aggregations"][0]["group_value"] == "Apex"
    assert payload["results"]["aggregations"][0]["metric_value"] == 13500.0


def test_nl_query_lists_problematic_records(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Mutasd a warning es invalid rekordokat."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is True
    assert payload["recognized_intent"] == "list_records"
    assert payload["query_plan"]["filters"]["validation_statuses"] == ["warning", "invalid"]
    assert payload["result_type"] == "records"
    assert payload["results"]["count"] == 2
    assert {item["validation_status"] for item in payload["results"]["records"]} == {"warning", "invalid"}


def test_nl_query_supports_location_records_and_top_group(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)

    location_response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Milyen rekordok vannak North locationre?"},
    )
    assert location_response.status_code == 200
    location_payload = location_response.json()
    assert location_payload["supported"] is True
    assert location_payload["query_plan"]["filters"]["location"] == "north"
    assert location_payload["results"]["count"] == 3

    top_response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Melyik treatment mellett a legnagyobb az atlagos yield?"},
    )
    assert top_response.status_code == 200
    top_payload = top_response.json()
    assert top_payload["supported"] is True
    assert top_payload["recognized_intent"] == "top_group"
    assert top_payload["query_plan"]["group_by"] == "treatment"
    assert top_payload["result_type"] == "top_group"
    assert top_payload["results"]["top_group"]["group_value"] == "treated"
    assert top_payload["results"]["top_group"]["metric_value"] == 15000.0


def test_nl_query_rejects_unsupported_questions(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))

    client = TestClient(app)
    response = client.post(
        "/api/harmonized/nl-query",
        json={"question": "Rajzolj diagramot a teljes trendrol."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is False
    assert payload["recognized_intent"] == "unsupported"
    assert payload["result_type"] == "unsupported"
    assert payload["results"]["count"] == 0

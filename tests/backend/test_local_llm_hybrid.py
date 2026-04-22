from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.llm import audit as llm_audit
from backend.app.llm.client import LLMCallResult
from backend.app.llm.config import LocalLLMConfig
from backend.app.llm import planner_adapter
from backend.app.llm.prompts import compact_schema_snapshot_for_llm
from backend.app.main import app
from backend.app.mcp import audit as mcp_audit
from backend.app.mcp.tools import core_tools
from backend.app.services import harmonized_query_service
from backend.app.services.uploads import session_service
from backend.app.text_to_sql import planner, sql_executor
from backend.app.text_to_sql.models import QueryPlan
from tests.backend.fake_db import FakeDatabase, fake_get_conn
from tests.backend.test_harmonized_query_api import _seed_harmonized_rows


def _patch_dependencies(monkeypatch, db: FakeDatabase) -> None:
    monkeypatch.setattr(harmonized_query_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(session_service, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(mcp_audit, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(llm_audit, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(sql_executor, "get_conn", lambda: fake_get_conn(db))
    monkeypatch.setattr(planner, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)
    monkeypatch.setattr(core_tools, "get_harmonized_query_metadata", harmonized_query_service.get_harmonized_query_metadata)


def _enabled_config(*, orchestration: bool = False) -> LocalLLMConfig:
    return LocalLLMConfig(
        enabled=True,
        hybrid_enabled=True,
        tool_orchestration_enabled=orchestration,
        endpoint="http://local-llm.test/v1/chat/completions",
        model_name="mock-planner",
        api_key=None,
        timeout_ms=1000,
        max_output_tokens=512,
        temperature=0.0,
    )


def test_hybrid_mode_uses_valid_llm_plan(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config())

    proposal = {
        "decision": "propose_plan",
        "confidence": 0.86,
        "notes": ["LLM mapped 'output' to canonical yield and 'cultivar' to variety."],
        "query_plan": {
            "status": "supported",
            "intent": "aggregate",
            "source_relation": "safe.harmonized_observations_v1",
            "selected_measures": ["yield"],
            "selected_dimensions": ["variety"],
            "filters": [
                {"field_name": "variable", "operator": "eq", "value": "yield", "source_text": "output"},
                {"field_name": "normalized_unit", "operator": "eq", "value": "kg/ha", "source_text": "kg/ha"},
            ],
            "aggregations": [{"function": "avg", "field_name": "normalized_value", "alias": "metric_value"}],
            "grouping": ["variety"],
            "ordering": [{"field_name": "variety", "direction": "asc", "source_text": "cultivar"}],
            "limit": 25,
            "unit_handling": {"mode": "canonical_normalized", "normalized_unit": "kg/ha", "note": "yield"},
            "ambiguity_flags": [],
            "validation_notes": ["LLM-assisted plan"],
            "trace": [{"source_text": "output", "mapped_to": "measure:yield", "note": None}],
            "target_measure": "yield",
            "result_type": "aggregation",
        },
    }

    monkeypatch.setattr(
        planner_adapter.LocalLLMClient,
        "chat_completion",
        lambda self, *, messages: LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={"choices": [{"message": {"content": json.dumps(proposal)}}]},
            content=json.dumps(proposal),
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "mean output by cultivar", "mode": "local_llm_hybrid"},
        headers={"X-Correlation-Id": "corr-hybrid-valid"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "supported"
    assert payload["planning_metadata"]["plan_origin"] == "local_llm"
    assert payload["planning_metadata"]["llm_used"] is True
    assert payload["result_type"] == "aggregation"

    llm_audit_response = client.get("/api/llm/audit", params={"correlation_id": "corr-hybrid-valid"})
    assert llm_audit_response.status_code == 200
    assert llm_audit_response.json()["count"] == 1


def test_hybrid_mode_falls_back_on_invalid_llm_output(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config())
    monkeypatch.setattr(
        planner_adapter.LocalLLMClient,
        "chat_completion",
        lambda self, *, messages: LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={"choices": [{"message": {"content": "{\"not\":\"a plan\"}"}}]},
            content='{"not":"a plan"}',
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "mean output by cultivar", "mode": "local_llm_hybrid"},
        headers={"X-Correlation-Id": "corr-hybrid-invalid"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "clarification_required"
    assert payload["planning_metadata"]["fallback_used"] is True
    assert payload["planning_metadata"]["fallback_reason"] == "invalid_llm_output"
    assert payload["generated_sql"] is None


def test_hybrid_mode_accepts_common_llm_json_shape_variants(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config())
    monkeypatch.setattr(
        planner_adapter.LocalLLMClient,
        "chat_completion",
        lambda self, *, messages: LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "reject",
                                    "confidence": 0.1,
                                    "notes": "Need a narrower question.",
                                    "query_plan": {
                                        "status": "unsupported",
                                        "intent": "unsupported",
                                    },
                                }
                            )
                        }
                    }
                ]
            },
            content=json.dumps(
                {
                    "decision": "reject",
                    "confidence": 0.1,
                    "notes": "Need a narrower question.",
                    "query_plan": {
                        "status": "unsupported",
                        "intent": "unsupported",
                    },
                }
            ),
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "minden adat", "mode": "local_llm_hybrid"},
        headers={"X-Correlation-Id": "corr-hybrid-shape-variants"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_metadata"]["llm_output_valid"] is True
    assert payload["planning_metadata"]["fallback_reason"] == "reject"


def test_hybrid_mode_salvages_semantic_llm_plan_into_supported_query(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config())
    monkeypatch.setattr(
        planner_adapter.LocalLLMClient,
        "chat_completion",
        lambda self, *, messages: LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "propose_plan",
                                    "confidence": 0.85,
                                    "notes": "Typo-corrected average yield by variety.",
                                    "query_plan": {
                                        "status": "proposed",
                                        "intent": "calculate_average_yield_by_variety",
                                        "source_relation": "safe.harmonized_observations_v1",
                                        "selected_measures": ["yield"],
                                        "selected_dimensions": ["variety"],
                                        "filters": [],
                                        "aggregations": [{"measure": "yield", "aggregation": "avg_normalized_value"}],
                                        "grouping": ["variety"],
                                        "ordering": [],
                                        "limit": 25,
                                        "unit_handling": {"mode": "none", "normalized_unit": None, "note": None},
                                    },
                                }
                            )
                        }
                    }
                ]
            },
            content=json.dumps(
                {
                    "decision": "propose_plan",
                    "confidence": 0.85,
                    "notes": "Typo-corrected average yield by variety.",
                    "query_plan": {
                        "status": "proposed",
                        "intent": "calculate_average_yield_by_variety",
                        "source_relation": "safe.harmonized_observations_v1",
                        "selected_measures": ["yield"],
                        "selected_dimensions": ["variety"],
                        "filters": [],
                        "aggregations": [{"measure": "yield", "aggregation": "avg_normalized_value"}],
                        "grouping": ["variety"],
                        "ordering": [],
                        "limit": 25,
                        "unit_handling": {"mode": "none", "normalized_unit": None, "note": None},
                    },
                }
            ),
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "Mi átlagos hozm fjtánként?", "mode": "local_llm_hybrid"},
        headers={"X-Correlation-Id": "corr-hybrid-semantic-salvage"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "supported"
    assert payload["planning_metadata"]["llm_used"] is True
    assert payload["query_plan"]["intent"] == "aggregate"
    assert payload["query_plan"]["target_measure"] == "yield"
    filter_names = [item["field_name"] for item in payload["query_plan"]["filters"]]
    assert "variable" in filter_names
    assert "normalized_unit" in filter_names


def test_tool_orchestrated_mode_uses_safe_helper_tools(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config(orchestration=True))

    calls = iter(
        [
            {
                "confidence": 0.8,
                "notes": ["Need schema context first."],
                "steps": [{"tool_name": "describe_schema", "arguments": {"include_live_metadata": True}}],
            },
            {
                "decision": "propose_plan",
                "confidence": 0.84,
                "notes": ["Schema-assisted local plan."],
                "query_plan": {
                    "status": "supported",
                    "intent": "aggregate",
                    "source_relation": "safe.harmonized_observations_v1",
                    "selected_measures": ["yield"],
                    "selected_dimensions": ["variety"],
                    "filters": [
                        {"field_name": "variable", "operator": "eq", "value": "yield", "source_text": "output"},
                        {"field_name": "normalized_unit", "operator": "eq", "value": "kg/ha", "source_text": "kg/ha"},
                    ],
                    "aggregations": [{"function": "avg", "field_name": "normalized_value", "alias": "metric_value"}],
                    "grouping": ["variety"],
                    "ordering": [{"field_name": "variety", "direction": "asc", "source_text": "cultivar"}],
                    "limit": 25,
                    "unit_handling": {"mode": "canonical_normalized", "normalized_unit": "kg/ha", "note": "yield"},
                    "ambiguity_flags": [],
                    "validation_notes": ["LLM-assisted plan"],
                    "trace": [],
                    "target_measure": "yield",
                    "result_type": "aggregation",
                },
            },
        ]
    )

    def _mock_chat_completion(self, *, messages):
        payload = next(calls)
        return LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={"choices": [{"message": {"content": json.dumps(payload)}}]},
            content=json.dumps(payload),
        )

    monkeypatch.setattr(planner_adapter.LocalLLMClient, "chat_completion", _mock_chat_completion)

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "mean output by cultivar", "mode": "local_llm_tool_orchestrated"},
        headers={"X-Correlation-Id": "corr-tool-orchestrated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_metadata"]["orchestration_used"] is True
    assert payload["planning_metadata"]["orchestration_steps"] == ["describe_schema"]

    audit_response = client.get("/api/mcp/audit", params={"correlation_id": "corr-tool-orchestrated"})
    assert audit_response.status_code == 200
    tool_names = [item["tool_name"] for item in audit_response.json()["items"]]
    assert "describe_schema" in tool_names


def test_compact_schema_snapshot_for_llm_removes_large_value_lists() -> None:
    compact = compact_schema_snapshot_for_llm(
        {
            "safe_relations": [
                {
                    "relation_name": "safe.harmonized_observations_v1",
                    "description": "safe",
                    "columns": [{"name": "variety", "type": "text", "role": "dimension"}],
                }
            ],
            "canonical_dimensions": [
                {
                    "name": "variety",
                    "description": "dimension",
                    "aliases": ["variety", "cultivar", "genotype", "hybrid", "line", "entry", "material"],
                }
            ],
            "canonical_measures": [],
            "validation_statuses": {"valid": "ok"},
            "quality_flags": {"missing_unit": "warn"},
            "query_metadata": {
                "supported_filters": ["variable"],
                "supported_group_bys": ["variety"],
                "supported_metrics": ["avg_normalized_value"],
                "supported_validation_statuses": ["valid", "warning", "invalid"],
                "supported_quality_flags": ["missing_unit"],
                "available_variables": ["yield"],
                "available_normalized_units": ["kg/ha"],
                "available_varieties": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
                "available_locations": ["L1", "L2"],
                "available_treatments": ["T1", "T2"],
                "available_plot_ids": ["P1", "P2", "P3", "P4"],
                "aggregations_exclude_invalid_by_default": True,
            },
            "limits": {"default_limit": 25},
        }
    )

    query_metadata = compact["query_metadata"]
    assert "available_plot_ids" not in query_metadata
    assert query_metadata["available_varieties_sample"] == ["A", "B", "C", "D", "E", "F", "G", "H"]
    assert compact["canonical_dimensions"][0]["aliases"] == ["variety", "cultivar", "genotype", "hybrid", "line", "entry"]


def test_hybrid_mode_allows_llm_attempt_for_too_broad_deterministic_plan(monkeypatch) -> None:
    db = FakeDatabase()
    _seed_harmonized_rows(db)
    _patch_dependencies(monkeypatch, db)
    monkeypatch.setattr(planner_adapter, "load_local_llm_config", lambda: _enabled_config())

    broad_plan = QueryPlan(
        status="unsupported",
        intent="unsupported",
        source_relation="safe.harmonized_observations_v1",
        ambiguity_flags=["too_broad_request"],
        validation_notes=["Broad raw dump style requests are rejected."],
        result_type="unsupported",
        limit=25,
    )

    monkeypatch.setattr(
        planner_adapter,
        "plan_question",
        lambda **kwargs: (broad_plan, list(broad_plan.validation_notes)),
    )
    monkeypatch.setattr(
        planner_adapter.LocalLLMClient,
        "chat_completion",
        lambda self, *, messages: LLMCallResult(
            success=True,
            request_payload={"messages": messages},
            response_payload={"choices": [{"message": {"content": json.dumps({"decision": "clarify", "confidence": 0.7, "notes": ["Need a narrower question."], "query_plan": None})}}]},
            content=json.dumps({"decision": "clarify", "confidence": 0.7, "notes": ["Need a narrower question."], "query_plan": None}),
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/text-to-sql/query",
        json={"question": "minden adat", "mode": "local_llm_hybrid"},
        headers={"X-Correlation-Id": "corr-broad-llm-attempt"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_metadata"]["requested_mode"] == "local_llm_hybrid"
    assert payload["planning_metadata"]["fallback_used"] is True
    assert payload["planning_metadata"]["fallback_reason"] == "clarify"
    assert payload["planning_metadata"]["llm_output_valid"] is True

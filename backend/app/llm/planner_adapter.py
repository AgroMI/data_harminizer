from __future__ import annotations

import json
import time
from typing import Any

from backend.app.llm.audit import log_llm_call
from backend.app.llm.client import LocalLLMClient
from backend.app.llm.config import load_local_llm_config
from backend.app.llm.models import (
    LLMPlannerProposal,
    LLMToolOrchestrationProposal,
)
from backend.app.llm.types import PipelineMode, PlanningMetadata
from backend.app.llm.prompts import build_planner_messages, build_tool_selection_messages
from backend.app.text_to_sql.catalog import (
    FORBIDDEN_REQUEST_TERMS,
    SAFE_FILTER_FIELDS,
    SAFE_GROUP_FIELDS,
    SAFE_PROJECTION_COLUMNS,
    SAFE_RELATION_NAME,
)
from backend.app.text_to_sql.models import QueryPlan
from backend.app.text_to_sql.planner import plan_question
from backend.app.text_to_sql.catalog import build_schema_snapshot
from backend.app.services.harmonized_query_service import get_harmonized_query_metadata
from etl.unit_harmonization import canonical_unit_for_measure

ORCHESTRATION_ALLOWLIST = ("describe_schema", "explain_metadata", "retrieve_evidence")
ORCHESTRATION_MAX_STEPS = 3


def plan_question_with_optional_llm(
    *,
    question: str,
    upload_session_id: str | None = None,
    limit_override: int | None = None,
    mode: PipelineMode = "deterministic",
    correlation_id: str | None = None,
) -> tuple[QueryPlan, list[str], PlanningMetadata]:
    deterministic_plan, deterministic_explanation = plan_question(
        question=question,
        upload_session_id=upload_session_id,
        limit_override=limit_override,
    )
    metadata = PlanningMetadata(
        requested_mode=mode,
        applied_mode=mode if mode != "deterministic" else "deterministic",
        plan_origin="deterministic",
    )

    if mode == "deterministic":
        return deterministic_plan, deterministic_explanation, metadata

    config = load_local_llm_config()
    if not config.available or not config.hybrid_enabled:
        metadata.applied_mode = "deterministic"
        metadata.fallback_used = True
        metadata.fallback_reason = "local_llm_disabled"
        return deterministic_plan, deterministic_explanation, metadata

    if _is_deterministic_plan_good_enough(deterministic_plan):
        return deterministic_plan, deterministic_explanation, metadata

    if _is_hard_reject_case(question=question, deterministic_plan=deterministic_plan):
        metadata.fallback_used = True
        metadata.fallback_reason = "deterministic_hard_reject"
        return deterministic_plan, deterministic_explanation, metadata

    tool_context: list[dict[str, Any]] = []
    if mode == "local_llm_tool_orchestrated" and config.tool_orchestration_enabled:
        tool_context, orchestration_steps = _run_optional_tool_orchestration(
            question=question,
            deterministic_plan=deterministic_plan,
            correlation_id=correlation_id,
        )
        if orchestration_steps:
            metadata.orchestration_used = True
            metadata.orchestration_steps = orchestration_steps

    llm_result = _call_llm_planner(
        question=question,
        deterministic_plan=deterministic_plan,
        requested_mode=mode,
        tool_context=tool_context,
        correlation_id=correlation_id,
        config=config,
    )
    metadata.llm_attempted = True
    metadata.llm_output_valid = llm_result["output_valid"]

    proposal = llm_result["proposal"]
    if proposal is None:
        metadata.applied_mode = "deterministic"
        metadata.fallback_used = True
        metadata.fallback_reason = llm_result["fallback_reason"]
        return deterministic_plan, deterministic_explanation, metadata

    if proposal.decision != "propose_plan" or proposal.query_plan is None:
        metadata.applied_mode = "deterministic"
        metadata.fallback_used = True
        metadata.fallback_reason = proposal.decision
        explanation = deterministic_explanation + list(proposal.notes)
        return deterministic_plan, explanation, metadata

    validation_errors = validate_llm_query_plan(proposal.query_plan)
    if validation_errors:
        metadata.applied_mode = "deterministic"
        metadata.fallback_used = True
        metadata.fallback_reason = "invalid_llm_plan"
        explanation = deterministic_explanation + validation_errors
        return deterministic_plan, explanation, metadata

    metadata.plan_origin = "local_llm"
    metadata.llm_used = True
    return proposal.query_plan, list(proposal.notes), metadata


def validate_llm_query_plan(plan: QueryPlan) -> list[str]:
    errors: list[str] = []
    if plan.source_relation != SAFE_RELATION_NAME:
        errors.append("LLM plan must target the safe relation only.")
    for item in plan.filters:
        if item.field_name not in SAFE_FILTER_FIELDS:
            errors.append(f"Unsupported filter field in LLM plan: {item.field_name}.")
    for item in plan.grouping:
        if item not in SAFE_GROUP_FIELDS:
            errors.append(f"Unsupported grouping field in LLM plan: {item}.")
    for item in plan.selected_dimensions:
        if item not in SAFE_GROUP_FIELDS:
            errors.append(f"Unsupported selected dimension in LLM plan: {item}.")
    for item in plan.ordering:
        if item.field_name not in {*SAFE_GROUP_FIELDS, "observation_date", "variable", "metric_value"}:
            errors.append(f"Unsupported ordering field in LLM plan: {item.field_name}.")
    for item in plan.aggregations:
        if item.function == "avg" and item.field_name != "normalized_value":
            errors.append("Average aggregations must target normalized_value.")
        if item.function == "count" and item.field_name != "*":
            errors.append("Count aggregations must use '*'.")
    if plan.intent == "aggregate" and not plan.aggregations:
        errors.append("Aggregate plans must contain at least one aggregation.")
    if plan.intent == "select_records" and plan.aggregations:
        errors.append("Record plans must not contain aggregations.")
    if plan.result_type not in {"records", "aggregation", "unsupported"}:
        errors.append("Unsupported result_type in LLM plan.")
    return errors


def _is_deterministic_plan_good_enough(plan: QueryPlan) -> bool:
    return plan.supported and not plan.ambiguity_flags


def _is_hard_reject_case(*, question: str, deterministic_plan: QueryPlan) -> bool:
    normalized = question.casefold()
    if any(term in normalized for term in FORBIDDEN_REQUEST_TERMS):
        return True
    return "unsafe_request" in deterministic_plan.ambiguity_flags


def _run_optional_tool_orchestration(
    *,
    question: str,
    deterministic_plan: QueryPlan,
    correlation_id: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from backend.app.mcp.server import default_mcp_server

    config = load_local_llm_config()
    client = LocalLLMClient(config)
    available_tools = [
        tool
        for tool in default_mcp_server().list_tools()
        if tool["tool_name"] in ORCHESTRATION_ALLOWLIST
    ]
    messages = build_tool_selection_messages(
        question=question,
        deterministic_plan=deterministic_plan.model_dump(mode="json"),
        available_tools=available_tools,
    )
    started_at = time.perf_counter()
    result = client.chat_completion(messages=messages)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    proposal = _parse_json_payload(result.content, LLMToolOrchestrationProposal) if result.success else None
    output_valid = proposal is not None
    log_llm_call(
        correlation_id=correlation_id or "local-tool-orchestration",
        mode="local_llm_tool_orchestrated",
        provider="openai_compatible_http",
        model_name=config.model_name,
        prompt_template="tool_selection_v1",
        success=result.success,
        output_valid=output_valid,
        fallback_used=not output_valid,
        error_code=result.error_code,
        duration_ms=duration_ms,
        request_payload=result.request_payload,
        response_payload=result.response_payload,
    )
    if proposal is None:
        return [], []

    context: list[dict[str, Any]] = []
    steps: list[str] = []
    for step in proposal.steps[:ORCHESTRATION_MAX_STEPS]:
        if step.tool_name not in ORCHESTRATION_ALLOWLIST:
            continue
        response = default_mcp_server().invoke_by_name(
            tool_name=step.tool_name,
            arguments=step.arguments,
            correlation_id=correlation_id,
        )
        steps.append(step.tool_name)
        if response.get("success"):
            context.append(
                {
                    "tool_name": step.tool_name,
                    "result": response.get("result"),
                }
            )
    return context, steps


def _call_llm_planner(
    *,
    question: str,
    deterministic_plan: QueryPlan,
    requested_mode: PipelineMode,
    tool_context: list[dict[str, Any]],
    correlation_id: str | None,
    config: Any,
) -> dict[str, Any]:
    client = LocalLLMClient(config)
    schema_snapshot = build_schema_snapshot(get_harmonized_query_metadata())
    messages = build_planner_messages(
        question=question,
        deterministic_plan=deterministic_plan.model_dump(mode="json"),
        schema_snapshot=schema_snapshot,
        requested_mode=requested_mode,
        tool_context=tool_context,
    )
    started_at = time.perf_counter()
    result = client.chat_completion(messages=messages)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    proposal = _parse_json_payload(result.content, LLMPlannerProposal) if result.success else None
    output_valid = proposal is not None
    fallback_reason = result.error_code or "invalid_llm_output"
    log_llm_call(
        correlation_id=correlation_id or "local-llm-plan",
        mode=requested_mode,
        provider="openai_compatible_http",
        model_name=config.model_name,
        prompt_template="hybrid_query_plan_v1",
        success=result.success,
        output_valid=output_valid,
        fallback_used=proposal is None,
        error_code=result.error_code,
        duration_ms=duration_ms,
        request_payload=result.request_payload,
        response_payload=result.response_payload,
    )
    return {
        "proposal": proposal,
        "output_valid": output_valid,
        "fallback_reason": fallback_reason,
    }


def _parse_json_payload(content: str | None, model_type: Any) -> Any | None:
    if not content:
        return None
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.startswith("json"):
            normalized = normalized[4:].strip()
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return None
    payload = _normalize_llm_payload(payload=payload, model_type=model_type)
    try:
        return model_type.model_validate(payload)
    except Exception:
        return None


def _normalize_llm_payload(*, payload: Any, model_type: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if model_type is LLMPlannerProposal:
        normalized = dict(payload)
        if isinstance(normalized.get("notes"), str):
            normalized["notes"] = [normalized["notes"]]
        query_plan = normalized.get("query_plan")
        if isinstance(query_plan, dict):
            normalized["query_plan"] = _normalize_query_plan_payload(query_plan)
        return normalized

    if model_type is LLMToolOrchestrationProposal:
        normalized = dict(payload)
        if isinstance(normalized.get("notes"), str):
            normalized["notes"] = [normalized["notes"]]
        if not isinstance(normalized.get("steps"), list):
            normalized["steps"] = []
        return normalized

    return payload


def _normalize_query_plan_payload(query_plan: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(query_plan)
    selected_measures = normalized.get("selected_measures")
    target_measure = selected_measures[0] if isinstance(selected_measures, list) and selected_measures else normalized.get("target_measure")

    if normalized.get("status") == "proposed":
        normalized["status"] = "supported"

    raw_intent = normalized.get("intent")
    if isinstance(raw_intent, str):
        lowered_intent = raw_intent.casefold()
        if lowered_intent in {"aggregate", "select_records", "unsupported", "clarification_required"}:
            pass
        elif "average" in lowered_intent or "count" in lowered_intent or normalized.get("aggregations"):
            normalized["intent"] = "aggregate"
        elif "record" in lowered_intent or "list" in lowered_intent or "show" in lowered_intent:
            normalized["intent"] = "select_records"
        elif normalized.get("status") == "clarification_required":
            normalized["intent"] = "clarification_required"
        else:
            normalized["intent"] = "unsupported"

    normalized.setdefault("source_relation", SAFE_RELATION_NAME)
    normalized.setdefault("selected_measures", [])
    normalized.setdefault("selected_dimensions", [])
    normalized.setdefault("filters", [])
    normalized["aggregations"] = _normalize_aggregation_payloads(normalized.get("aggregations"))
    normalized.setdefault("grouping", [])
    normalized.setdefault("ordering", [])
    normalized.setdefault("limit", 25)
    normalized.setdefault("unit_handling", {"mode": "none", "normalized_unit": None, "note": None})
    normalized.setdefault("ambiguity_flags", [])
    normalized.setdefault("validation_notes", [])
    normalized.setdefault("trace", [])
    normalized.setdefault("target_measure", target_measure)
    if normalized.get("intent") == "aggregate" and normalized.get("result_type") in {None, "unsupported"}:
        normalized["result_type"] = "aggregation"
    elif normalized.get("intent") == "select_records" and normalized.get("result_type") in {None, "unsupported"}:
        normalized["result_type"] = "records"
    else:
        normalized.setdefault("result_type", "unsupported")
    if isinstance(normalized.get("validation_notes"), str):
        normalized["validation_notes"] = [normalized["validation_notes"]]
    if isinstance(normalized.get("ambiguity_flags"), str):
        normalized["ambiguity_flags"] = [normalized["ambiguity_flags"]]

    filters = list(normalized.get("filters", []))
    if target_measure and not any(item.get("field_name") == "variable" for item in filters if isinstance(item, dict)):
        filters.append({"field_name": "variable", "operator": "eq", "value": target_measure, "source_text": target_measure})
    if target_measure and not any(item.get("field_name") == "normalized_unit" for item in filters if isinstance(item, dict)):
        filters.append(
            {
                "field_name": "normalized_unit",
                "operator": "eq",
                "value": canonical_unit_for_measure(target_measure),
                "source_text": canonical_unit_for_measure(target_measure),
            }
        )
    normalized["filters"] = filters

    if (
        normalized.get("intent") != "select_records"
        and target_measure
        and normalized.get("grouping")
        and not normalized.get("aggregations")
    ):
        normalized["intent"] = "aggregate"
        normalized["status"] = "supported"
        normalized["result_type"] = "aggregation"
        normalized["aggregations"] = [{"function": "avg", "field_name": "normalized_value", "alias": "metric_value"}]

    if normalized.get("intent") == "aggregate" and normalized.get("status") != "supported":
        normalized["status"] = "supported"
    return normalized


def _normalize_aggregation_payloads(raw_aggregations: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_aggregations, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_aggregations:
        if not isinstance(item, dict):
            continue
        if {"function", "field_name", "alias"}.issubset(item.keys()):
            normalized.append(item)
            continue

        aggregation_name = str(item.get("aggregation", "")).casefold()
        if aggregation_name in {"avg", "average", "avg_normalized_value"}:
            normalized.append({"function": "avg", "field_name": "normalized_value", "alias": "metric_value"})
            continue
        if aggregation_name == "count":
            normalized.append({"function": "count", "field_name": "*", "alias": "metric_value"})
            continue
    return normalized

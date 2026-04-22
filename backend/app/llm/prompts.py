from __future__ import annotations

import difflib
import json
import unicodedata
from typing import Any

MAX_ALIAS_COUNT = 6
MAX_SAMPLE_VALUES = 8
MAX_HINT_COUNT = 6

PLANNER_FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "question": "yield by cultivar",
        "expected_decision": "propose_plan",
        "reason": "Cultivar is a variety-like grouping and plain 'measure by dimension' wording should be treated as a bounded aggregation.",
        "query_plan": {
            "status": "supported",
            "intent": "aggregate",
            "selected_measures": ["yield"],
            "selected_dimensions": ["variety"],
            "grouping": ["variety"],
            "aggregations": [{"function": "avg", "field_name": "normalized_value", "alias": "metric_value"}],
            "result_type": "aggregation",
        },
    },
    {
        "question": "show invalid records",
        "expected_decision": "propose_plan",
        "reason": "Explicit record-list wording should map to a bounded record query, not an aggregation.",
        "query_plan": {
            "status": "supported",
            "intent": "select_records",
            "selected_measures": [],
            "selected_dimensions": [],
            "grouping": [],
            "aggregations": [],
            "result_type": "records",
        },
    },
]


def build_planner_messages(
    *,
    question: str,
    deterministic_plan: dict[str, Any],
    schema_snapshot: dict[str, Any],
    requested_mode: str,
    tool_context: list[dict[str, Any]],
) -> list[dict[str, str]]:
    compact_schema_snapshot = compact_schema_snapshot_for_llm(schema_snapshot)
    lexical_hints = build_lexical_hints(question=question, schema_snapshot=compact_schema_snapshot)
    user_payload = {
        "question": question,
        "requested_mode": requested_mode,
        "deterministic_plan": deterministic_plan,
        "schema_snapshot": compact_schema_snapshot,
        "lexical_hints": lexical_hints,
        "few_shot_examples": PLANNER_FEW_SHOT_EXAMPLES,
        "tool_context": tool_context,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a local planning helper for a read-only agricultural text-to-SQL system. "
                "Never return SQL. Never ask for database access. "
                "Return a JSON object only, with keys: decision, confidence, notes, query_plan. "
                "query_plan must be a strict structured proposal compatible with the provided schema. "
                "The deterministic_plan may be incomplete, over-reject broadness, or miss user typos. "
                "Use lexical_hints to recover likely misspellings and semantic wording variants. "
                "Do not require exact alias overlap when the semantic meaning is still clear. "
                "Agricultural production, harvest outcome, crop output, or similar wording can map to the canonical measure yield. "
                "Cultivar-, genotype-, hybrid-, or variety-like grouping can map to the canonical dimension variety. "
                "Fertilizer, treatment, or management variant wording can map to treatment. "
                "Site, station, field, or farm wording can map to location. "
                "When a user asks for a measure by a dimension, and there is no explicit list-record wording, prefer a bounded aggregate interpretation. "
                "For example, 'yield by variety' or semantically equivalent phrasing should normally become an average aggregation grouped by variety. "
                "If a safe bounded interpretation is plausible, prefer propose_plan over reject. "
                "Only use clarify or reject when no bounded canonical interpretation is defensible."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=True),
        },
    ]


def compact_schema_snapshot_for_llm(schema_snapshot: dict[str, Any]) -> dict[str, Any]:
    safe_relations = []
    for relation in schema_snapshot.get("safe_relations", []):
        if not isinstance(relation, dict):
            continue
        safe_relations.append(
            {
                "relation_name": relation.get("relation_name"),
                "description": relation.get("description"),
                "columns": [
                    {
                        "name": column.get("name"),
                        "type": column.get("type"),
                        "role": column.get("role"),
                    }
                    for column in relation.get("columns", [])
                    if isinstance(column, dict)
                ],
            }
        )

    canonical_dimensions = []
    for item in schema_snapshot.get("canonical_dimensions", []):
        if not isinstance(item, dict):
            continue
        canonical_dimensions.append(
            {
                "name": item.get("name"),
                "description": item.get("description"),
                "aliases": list(item.get("aliases", [])[:MAX_ALIAS_COUNT]),
            }
        )

    canonical_measures = []
    for item in schema_snapshot.get("canonical_measures", []):
        if not isinstance(item, dict):
            continue
        canonical_measures.append(
            {
                "name": item.get("name"),
                "description": item.get("description"),
                "aliases": list(item.get("aliases", [])[:MAX_ALIAS_COUNT]),
                "canonical_unit": item.get("canonical_unit"),
            }
        )

    query_metadata = schema_snapshot.get("query_metadata", {})
    compact_query_metadata = {
        "supported_filters": list(query_metadata.get("supported_filters", [])),
        "supported_group_bys": list(query_metadata.get("supported_group_bys", [])),
        "supported_metrics": list(query_metadata.get("supported_metrics", [])),
        "supported_validation_statuses": list(query_metadata.get("supported_validation_statuses", [])),
        "supported_quality_flags": list(query_metadata.get("supported_quality_flags", [])),
        "available_variables": list(query_metadata.get("available_variables", [])),
        "available_normalized_units": list(query_metadata.get("available_normalized_units", [])),
        "available_varieties_sample": list(query_metadata.get("available_varieties", [])[:MAX_SAMPLE_VALUES]),
        "available_locations_sample": list(query_metadata.get("available_locations", [])[:MAX_SAMPLE_VALUES]),
        "available_treatments_sample": list(query_metadata.get("available_treatments", [])[:MAX_SAMPLE_VALUES]),
        "aggregations_exclude_invalid_by_default": query_metadata.get("aggregations_exclude_invalid_by_default", True),
    }

    return {
        "safe_relations": safe_relations,
        "canonical_dimensions": canonical_dimensions,
        "canonical_measures": canonical_measures,
        "validation_statuses": schema_snapshot.get("validation_statuses", {}),
        "quality_flags": schema_snapshot.get("quality_flags", {}),
        "query_metadata": compact_query_metadata,
        "limits": schema_snapshot.get("limits", {}),
    }


def build_lexical_hints(*, question: str, schema_snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized_tokens = _tokenize(question)
    aggregation_aliases = {
        "avg": ["average", "avg", "mean"],
        "count": ["count", "how many"],
    }

    measure_aliases: dict[str, list[str]] = {}
    for item in schema_snapshot.get("canonical_measures", []):
        if not isinstance(item, dict):
            continue
        aliases = [str(alias) for alias in item.get("aliases", [])]
        measure_aliases[str(item.get("name"))] = aliases

    dimension_aliases: dict[str, list[str]] = {}
    for item in schema_snapshot.get("canonical_dimensions", []):
        if not isinstance(item, dict):
            continue
        aliases = [str(alias) for alias in item.get("aliases", [])]
        dimension_aliases[str(item.get("name"))] = aliases

    return {
        "matched_measures": _collect_close_matches(normalized_tokens, measure_aliases),
        "matched_dimensions": _collect_close_matches(normalized_tokens, dimension_aliases),
        "matched_aggregations": _collect_close_matches(normalized_tokens, aggregation_aliases),
    }


def _collect_close_matches(tokens: list[str], alias_catalog: dict[str, list[str]]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for token in tokens:
        if len(token) < 3:
            continue
        for canonical_name, aliases in alias_catalog.items():
            normalized_aliases = {_normalize_token(alias): alias for alias in aliases if alias}
            best = difflib.get_close_matches(token, list(normalized_aliases.keys()), n=1, cutoff=0.72)
            if best:
                matches.append(
                    {
                        "token": token,
                        "canonical_name": canonical_name,
                        "matched_alias": normalized_aliases[best[0]],
                    }
                )
    return matches[:MAX_HINT_COUNT]


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_token(text)
    return [token for token in normalized.replace("?", " ").replace(",", " ").split() if token]


def _normalize_token(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(char)
    )


def build_tool_selection_messages(
    *,
    question: str,
    deterministic_plan: dict[str, Any],
    available_tools: list[dict[str, Any]],
) -> list[dict[str, str]]:
    user_payload = {
        "question": question,
        "deterministic_plan": deterministic_plan,
        "available_tools": available_tools,
        "rules": {
            "max_steps": 3,
            "tool_allowlist": [tool["tool_name"] for tool in available_tools],
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a read-only MCP tool-selection helper. "
                "Return JSON only with keys: confidence, notes, steps. "
                "Choose at most 3 tools. Only use listed tools. "
                "Do not propose SQL execution tools for unsafe or broad questions."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=True),
        },
    ]

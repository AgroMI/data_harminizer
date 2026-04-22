from __future__ import annotations

import re
import unicodedata
from typing import Any

from backend.app.schemas import AggregationGroupBy, AggregationMetric
from backend.app.services.harmonized_query_service import (
    HarmonizedObservationFilters,
    aggregate_harmonized_observations,
    get_harmonized_query_metadata,
    list_harmonized_observations,
)
from etl.types import CanonicalMeasure, CanonicalUnit, ValidationStatus
from etl.unit_harmonization import canonical_unit_for_measure

NL_INTENT_UNSUPPORTED = "unsupported"
DEFAULT_LIST_LIMIT = 50
DEFAULT_PROBLEMATIC_LIMIT = 100

MEASURE_KEYWORDS: dict[CanonicalMeasure, tuple[str, ...]] = {
    "yield": ("yield",),
    "moisture": ("moisture",),
    "plant_height": ("plant height", "plant_height"),
}

GROUP_BY_KEYWORDS: dict[AggregationGroupBy, tuple[str, ...]] = {
    "variety": ("variety",),
    "treatment": ("treatment",),
    "location": ("location",),
    "validation_status": ("validation status", "status"),
}

AVERAGE_KEYWORDS: tuple[str, ...] = ("average", "avg", "mean")
TOP_KEYWORDS: tuple[str, ...] = ("highest", "largest", "maximum", "max")
LIST_KEYWORDS: tuple[str, ...] = ("show", "list", "records", "record")

WARNING_KEYWORDS: tuple[str, ...] = ("warning",)
INVALID_KEYWORDS: tuple[str, ...] = ("invalid",)


def execute_nl_query(
    *,
    question: str,
    upload_session_id: str | None = None,
    variable: CanonicalMeasure | None = None,
) -> dict[str, Any]:
    return build_nl_query_response(
        question=question,
        upload_session_id=upload_session_id,
        variable=variable,
    )


def build_nl_query_response(
    *,
    question: str,
    upload_session_id: str | None = None,
    variable: CanonicalMeasure | None = None,
) -> dict[str, Any]:
    metadata = get_harmonized_query_metadata()
    plan, supported, explanation = interpret_nl_query(question=question, metadata=metadata)
    _apply_query_scope_overrides(
        plan=plan,
        upload_session_id=upload_session_id,
        variable=variable,
    )

    if not supported:
        return {
            "question": question,
            "supported": False,
            "recognized_intent": plan["intent_type"],
            "query_plan": plan,
            "result_type": "unsupported",
            "results": {
                "records": [],
                "aggregations": [],
                "top_group": None,
                "count": 0,
            },
            "explanation": explanation,
        }

    explanation = _build_plan_explanation(plan)
    return _execute_supported_plan(
        question=question,
        plan=plan,
        explanation=explanation,
    )


def _apply_query_scope_overrides(
    *,
    plan: dict[str, Any],
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
) -> None:
    filters = plan["filters"]
    if upload_session_id:
        filters["upload_session_id"] = upload_session_id

    if variable is None:
        return

    plan["variable"] = variable
    filters["variable"] = variable
    filters["normalized_unit"] = canonical_unit_for_measure(variable)


def _execute_supported_plan(
    *,
    question: str,
    plan: dict[str, Any],
    explanation: str,
) -> dict[str, Any]:
    if plan["intent_type"] == "list_records":
        return _execute_list_plan(question=question, plan=plan, explanation=explanation)
    if plan["intent_type"] == "aggregate":
        return _execute_aggregation_plan(
            question=question,
            plan=plan,
            top_group=False,
            explanation=explanation,
        )
    if plan["intent_type"] == "top_group":
        return _execute_aggregation_plan(
            question=question,
            plan=plan,
            top_group=True,
            explanation=explanation,
        )

    return {
        "question": question,
        "supported": False,
        "recognized_intent": "unsupported",
        "query_plan": plan,
        "result_type": "unsupported",
        "results": {"records": [], "aggregations": [], "top_group": None, "count": 0},
        "explanation": "Unsupported query.",
    }


def _build_plan_explanation(plan: dict[str, Any]) -> str:
    if plan["intent_type"] == "list_records":
        return _build_list_explanation(plan)
    if plan["intent_type"] == "aggregate":
        return (
            f"Recognized an aggregation query for average normalized {plan['variable']} "
            f"grouped by {plan['group_by']}."
        )
    if plan["intent_type"] == "top_group":
        return (
            f"Recognized a top-group query over average normalized {plan['variable']} "
            f"grouped by {plan['group_by']}."
        )
    return "Unsupported query."


def interpret_nl_query(*, question: str, metadata: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool, str]:
    context = metadata or get_harmonized_query_metadata()
    normalized_question = _normalize_text(question)
    plan = _empty_plan()

    if not normalized_question:
        return plan, False, "The question is empty after normalization."

    variable = _detect_variable(normalized_question)
    group_by = _detect_group_by(normalized_question)
    matched_location = _match_available_value(normalized_question, context.get("available_locations", []))
    matched_variety = _match_available_value(normalized_question, context.get("available_varieties", []))
    matched_treatment = _match_available_value(normalized_question, context.get("available_treatments", []))
    matched_plot_id = _match_available_value(normalized_question, context.get("available_plot_ids", []))
    status_matches = _detect_validation_statuses(normalized_question)

    filters = plan["filters"]
    filters["location"] = matched_location
    filters["variety"] = matched_variety
    filters["treatment"] = matched_treatment
    filters["plot_id"] = matched_plot_id
    filters["validation_statuses"] = status_matches

    has_average = _contains_any(normalized_question, AVERAGE_KEYWORDS)
    has_top = _contains_any(normalized_question, TOP_KEYWORDS)
    has_listish = _contains_any(normalized_question, LIST_KEYWORDS)
    has_problematic_status = len(status_matches) > 0

    if variable is not None:
        plan["variable"] = variable
        filters["variable"] = variable

    if has_top and has_average and variable == "yield" and group_by in {"variety", "treatment", "location"}:
        plan["intent_type"] = "top_group"
        plan["group_by"] = group_by
        plan["metric"] = "avg_normalized_value"
        plan["include_invalid"] = False
        plan["top_k"] = 1
        filters["normalized_unit"] = canonical_unit_for_measure("yield")
        return plan, True, (
            f"Recognized a top-group query over average normalized yield grouped by {group_by}."
        )

    if has_average and variable is not None and group_by in {"variety", "treatment", "location"}:
        plan["intent_type"] = "aggregate"
        plan["group_by"] = group_by
        plan["metric"] = "avg_normalized_value"
        plan["include_invalid"] = False
        filters["normalized_unit"] = canonical_unit_for_measure(variable)
        return plan, True, (
            f"Recognized an aggregation query for average normalized {variable} grouped by {group_by}."
        )

    if has_problematic_status or has_listish or any(
        value is not None for value in (matched_location, matched_variety, matched_treatment, matched_plot_id, variable)
    ):
        plan["intent_type"] = "list_records"
        plan["include_invalid"] = "invalid" in status_matches
        plan["limit"] = DEFAULT_PROBLEMATIC_LIMIT if len(status_matches) > 1 else DEFAULT_LIST_LIMIT
        if len(status_matches) == 1:
            filters["validation_status"] = status_matches[0]
            filters["validation_statuses"] = []
        elif len(status_matches) > 1:
            filters["validation_status"] = None
            filters["validation_statuses"] = status_matches
        if variable is not None:
            filters["normalized_unit"] = canonical_unit_for_measure(variable)

        return plan, True, _build_list_explanation(plan)

    return plan, False, (
        "Unsupported query. Supported read-only patterns are average yield by variety/treatment/location, "
        "record listing by variable/variety/location, warning or invalid record listing, and highest average yield questions."
    )


def _execute_list_plan(
    *,
    question: str,
    plan: dict[str, Any],
    explanation: str,
) -> dict[str, Any]:
    filters = plan["filters"]
    statuses = list(filters.get("validation_statuses") or [])
    if statuses:
        items = _list_records_for_multiple_statuses(plan=plan, statuses=statuses)
    else:
        response = list_harmonized_observations(
            limit=plan["limit"],
            filters=_build_harmonized_filters(plan=plan),
        )
        items = response["items"]

    items = sorted(items, key=_observation_sort_key)[: plan["limit"]]

    return {
        "question": question,
        "supported": True,
        "recognized_intent": plan["intent_type"],
        "query_plan": plan,
        "result_type": "records",
        "results": {
            "records": items,
            "aggregations": [],
            "top_group": None,
            "count": len(items),
        },
        "explanation": explanation,
    }


def _execute_aggregation_plan(
    *,
    question: str,
    plan: dict[str, Any],
    top_group: bool,
    explanation: str,
) -> dict[str, Any]:
    response = aggregate_harmonized_observations(
        group_by=plan["group_by"],
        metric=plan["metric"],
        include_invalid=plan["include_invalid"],
        filters=_build_harmonized_filters(plan=plan),
    )
    items = response["items"]

    top_item = None
    result_type = "aggregation"
    if top_group:
        result_type = "top_group"
        top_item = _pick_top_group(items)

    return {
        "question": question,
        "supported": True,
        "recognized_intent": plan["intent_type"],
        "query_plan": plan,
        "result_type": result_type,
        "results": {
            "records": [],
            "aggregations": items,
            "top_group": top_item,
            "count": len(items),
        },
        "explanation": explanation,
    }


def _list_records_for_multiple_statuses(*, plan: dict[str, Any], statuses: list[ValidationStatus]) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, int, str]] = set()

    for status in statuses:
        filters = _build_harmonized_filters(plan=plan, validation_status=status)
        response = list_harmonized_observations(limit=plan["limit"], filters=filters)
        for item in response["items"]:
            key = (
                str(item["upload_session_id"]),
                str(item["source_sheet"]),
                int(item["source_row_index"]),
                str(item["source_column"]),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            combined.append(item)

    return combined


def _build_harmonized_filters(
    *,
    plan: dict[str, Any],
    validation_status: ValidationStatus | None = None,
) -> HarmonizedObservationFilters:
    filters = plan["filters"]
    return HarmonizedObservationFilters(
        upload_session_id=filters.get("upload_session_id"),
        variable=filters.get("variable"),
        variety=filters.get("variety"),
        location=filters.get("location"),
        treatment=filters.get("treatment"),
        plot_id=filters.get("plot_id"),
        observation_date_from=filters.get("observation_date_from"),
        observation_date_to=filters.get("observation_date_to"),
        validation_status=validation_status or filters.get("validation_status"),
        quality_flag=filters.get("quality_flag"),
        normalized_unit=filters.get("normalized_unit"),
    )


def _pick_top_group(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: (float(item["metric_value"]), str(item.get("group_value") or "")))


def _empty_plan() -> dict[str, Any]:
    return {
        "intent_type": NL_INTENT_UNSUPPORTED,
        "variable": None,
        "group_by": None,
        "metric": None,
        "filters": {
            "upload_session_id": None,
            "variable": None,
            "variety": None,
            "location": None,
            "treatment": None,
            "plot_id": None,
            "observation_date_from": None,
            "observation_date_to": None,
            "validation_status": None,
            "validation_statuses": [],
            "quality_flag": None,
            "normalized_unit": None,
        },
        "include_invalid": False,
        "limit": DEFAULT_LIST_LIMIT,
        "top_k": None,
    }


def _build_list_explanation(plan: dict[str, Any]) -> str:
    filters = plan["filters"]
    active_parts: list[str] = []
    for key in (
        "upload_session_id",
        "variable",
        "variety",
        "treatment",
        "location",
        "plot_id",
        "normalized_unit",
    ):
        value = filters.get(key)
        if value:
            active_parts.append(f"{key}={value}")

    statuses = filters.get("validation_statuses") or []
    if filters.get("validation_status"):
        active_parts.append(f"validation_status={filters['validation_status']}")
    elif statuses:
        active_parts.append(f"validation_statuses={','.join(statuses)}")

    if not active_parts:
        return "Recognized a read-only record listing query with no additional filters."
    return f"Recognized a read-only record listing query with filters: {', '.join(active_parts)}."


def _detect_variable(question: str) -> CanonicalMeasure | None:
    for variable, keywords in MEASURE_KEYWORDS.items():
        if _contains_any(question, keywords):
            return variable
    return None


def _detect_group_by(question: str) -> AggregationGroupBy | None:
    for group_by, keywords in GROUP_BY_KEYWORDS.items():
        if _contains_any(question, keywords):
            return group_by
    return None


def _detect_validation_statuses(question: str) -> list[ValidationStatus]:
    statuses: list[ValidationStatus] = []
    if _contains_any(question, WARNING_KEYWORDS):
        statuses.append("warning")
    if _contains_any(question, INVALID_KEYWORDS):
        statuses.append("invalid")
    return statuses


def _match_available_value(question: str, values: list[str] | tuple[str, ...]) -> str | None:
    normalized_pairs = sorted(
        [(_normalize_text(value), value) for value in values if value],
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for normalized_value, original_value in normalized_pairs:
        if normalized_value and normalized_value in question:
            return original_value
    return None


def _contains_any(question: str, keywords: tuple[str, ...]) -> bool:
    return any(_normalize_text(keyword) in question for keyword in keywords)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    compact = re.sub(r"[^a-z0-9%/]+", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def _observation_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    observation_date = item.get("observation_date")
    return (
        observation_date is None,
        observation_date or "",
        item.get("variable") or "",
        item.get("plot_id") is None,
        item.get("plot_id") or "",
        item.get("source_sheet") or "",
        item.get("source_row_index") or 0,
        item.get("source_column") or "",
    )

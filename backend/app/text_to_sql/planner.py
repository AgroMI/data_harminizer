from __future__ import annotations

import re
import unicodedata
from datetime import date as DateValue
from typing import Any

from backend.app.services.harmonized_query_service import get_harmonized_query_metadata
from backend.app.text_to_sql.catalog import (
    DEFAULT_RECORD_LIMIT,
    FORBIDDEN_REQUEST_TERMS,
    MAX_RECORD_LIMIT,
    SAFE_RELATION_NAME,
)
from backend.app.text_to_sql.models import (
    QueryAggregation,
    QueryDimensionField,
    QueryFilter,
    QueryOrdering,
    QueryPlan,
    QueryTraceItem,
    UnitHandling,
)
from etl.semantic_mapping import DIMENSION_TOKEN_MAP, MEASURE_TOKEN_MAP
from etl.types import CanonicalMeasure
from etl.unit_harmonization import canonical_unit_for_measure

AVERAGE_KEYWORDS: tuple[str, ...] = ("average", "avg", "mean")
COUNT_KEYWORDS: tuple[str, ...] = ("count", "how many", "record count")
TOP_KEYWORDS: tuple[str, ...] = ("highest", "largest", "top", "maximum", "max", "most")
LOW_KEYWORDS: tuple[str, ...] = ("lowest", "smallest", "minimum", "min")
LIST_KEYWORDS: tuple[str, ...] = ("show", "list", "records", "record")
WARNING_KEYWORDS: tuple[str, ...] = ("warning",)
INVALID_KEYWORDS: tuple[str, ...] = ("invalid",)
VALID_KEYWORDS: tuple[str, ...] = ("valid",)
ALL_DATA_KEYWORDS: tuple[str, ...] = ("all data", "entire dataset", "dump everything")

GROUPING_KEYWORDS: dict[QueryDimensionField, tuple[str, ...]] = {
    "plot_id": ("plot", "parcel", "plot id"),
    "variety": ("variety", "cultivar"),
    "treatment": ("treatment",),
    "location": ("location", "site"),
    "validation_status": ("validation status", "status"),
}


def plan_question(
    *,
    question: str,
    upload_session_id: str | None = None,
    limit_override: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[QueryPlan, list[str]]:
    context = metadata or get_harmonized_query_metadata()
    normalized_question = _normalize_text(question)
    plan = QueryPlan(
        status="unsupported",
        intent="unsupported",
        source_relation=SAFE_RELATION_NAME,
        limit=_resolve_limit(normalized_question, limit_override),
        result_type="unsupported",
    )

    if not normalized_question:
        plan.validation_notes.append("The question is empty after normalization.")
        return plan, list(plan.validation_notes)

    if any(term in normalized_question for term in FORBIDDEN_REQUEST_TERMS):
        plan.validation_notes.append("Unsafe or non-whitelisted request terms were detected.")
        plan.ambiguity_flags.append("unsafe_request")
        return plan, list(plan.validation_notes)

    matched_measures = _detect_measures(normalized_question)
    if len(matched_measures) > 1:
        plan.status = "clarification_required"
        plan.intent = "clarification_required"
        plan.ambiguity_flags.append("multiple_measures")
        plan.validation_notes.append("Multiple canonical measures were matched.")
        return plan, list(plan.validation_notes)

    measure = matched_measures[0] if matched_measures else None
    group_by = _detect_grouping(normalized_question)
    aggregation_function = _detect_aggregation_function(normalized_question)
    ordering = _detect_ordering(normalized_question)
    matched_filters = _detect_filters(normalized_question, context)
    date_filters = _detect_date_filters(normalized_question)

    trace: list[QueryTraceItem] = []
    if measure is not None:
        trace.append(QueryTraceItem(source_text=measure, mapped_to=f"measure:{measure}"))
    if group_by is not None:
        trace.append(QueryTraceItem(source_text=group_by, mapped_to=f"grouping:{group_by}"))
    for filter_item in matched_filters + date_filters:
        trace.append(
            QueryTraceItem(
                source_text=str(filter_item.value),
                mapped_to=f"filter:{filter_item.field_name}:{filter_item.operator}",
            )
        )

    plan.trace = trace
    plan.selected_measures = [measure] if measure is not None else []
    plan.target_measure = measure
    plan.grouping = [group_by] if group_by is not None else []
    plan.selected_dimensions = _selected_dimensions(group_by=group_by, filters=matched_filters)
    plan.filters.extend(matched_filters)
    plan.filters.extend(date_filters)
    plan.ordering = ordering

    if upload_session_id:
        plan.filters.append(
            QueryFilter(
                field_name="upload_session_id",
                operator="eq",
                value=upload_session_id,
                source_text=upload_session_id,
            )
        )

    status_filters = _detect_status_filters(normalized_question)
    if status_filters:
        filter_value: object = status_filters[0] if len(status_filters) == 1 else status_filters
        operator = "eq" if len(status_filters) == 1 else "in"
        plan.filters.append(
            QueryFilter(
                field_name="validation_status",
                operator=operator,
                value=filter_value,
                source_text="validation_status",
            )
        )
        plan.selected_dimensions = _append_if_missing(plan.selected_dimensions, "location" if group_by is None else group_by)

    if measure is not None:
        canonical_unit = canonical_unit_for_measure(measure)
        plan.filters.extend(
            [
                QueryFilter(field_name="variable", operator="eq", value=measure, source_text=measure),
                QueryFilter(
                    field_name="normalized_unit",
                    operator="eq",
                    value=canonical_unit,
                    source_text=canonical_unit,
                ),
            ]
        )
        plan.unit_handling = UnitHandling(
            mode="canonical_normalized",
            normalized_unit=canonical_unit,
            note=f"{measure} queries are normalized to {canonical_unit}.",
        )

    if aggregation_function is not None or _contains_any(normalized_question, TOP_KEYWORDS):
        return _plan_aggregate_query(
            plan=plan,
            aggregation_function=aggregation_function,
            group_by=group_by,
            measure=measure,
            normalized_question=normalized_question,
        )

    if _should_build_record_query(normalized_question, plan):
        if _is_overly_broad_request(normalized_question, plan):
            plan.validation_notes.append("Broad raw dump style requests are rejected.")
            plan.ambiguity_flags.append("too_broad_request")
            return plan, list(plan.validation_notes)

        plan.status = "supported"
        plan.intent = "select_records"
        plan.result_type = "records"
        plan.validation_notes.append("The query was mapped to a bounded read-only record listing.")
        if not plan.ordering:
            plan.ordering = [
                QueryOrdering(field_name="observation_date", direction="asc"),
                QueryOrdering(field_name="variable", direction="asc"),
            ]
        return plan, _explain_plan(plan)

    plan.validation_notes.append("No supported record or aggregation intent could be derived.")
    return plan, list(plan.validation_notes)


def _plan_aggregate_query(
    *,
    plan: QueryPlan,
    aggregation_function: str | None,
    group_by: CanonicalDimension | None,
    measure: CanonicalMeasure | None,
    normalized_question: str,
) -> tuple[QueryPlan, list[str]]:
    has_top = _contains_any(normalized_question, TOP_KEYWORDS) or _contains_any(normalized_question, LOW_KEYWORDS)
    if aggregation_function is None and has_top:
        aggregation_function = "avg" if measure is not None else "count"

    if aggregation_function == "avg" and measure is None:
        plan.status = "clarification_required"
        plan.intent = "clarification_required"
        plan.ambiguity_flags.append("missing_measure")
        plan.validation_notes.append("Average aggregation requires an explicit canonical measure.")
        return plan, list(plan.validation_notes)

    if has_top and group_by is None:
        plan.status = "clarification_required"
        plan.intent = "clarification_required"
        plan.ambiguity_flags.append("missing_grouping")
        plan.validation_notes.append("Top-N style aggregations require an explicit grouping dimension.")
        return plan, list(plan.validation_notes)

    if aggregation_function is None:
        plan.status = "unsupported"
        plan.intent = "unsupported"
        plan.validation_notes.append("Unsupported aggregation wording.")
        return plan, list(plan.validation_notes)

    plan.status = "supported"
    plan.intent = "aggregate"
    plan.result_type = "aggregation"
    plan.aggregations = [
        QueryAggregation(
            function=aggregation_function,
            field_name="normalized_value" if aggregation_function == "avg" else "*",
            alias="metric_value",
        )
    ]

    if aggregation_function == "avg" and not _has_filter(plan.filters, "validation_status"):
        plan.validation_notes.append("Invalid rows are excluded by default for average aggregations.")

    if has_top:
        direction = "asc" if _contains_any(normalized_question, LOW_KEYWORDS) else "desc"
        plan.ordering = [QueryOrdering(field_name="metric_value", direction=direction)]
        plan.limit = min(plan.limit, _extract_numeric_limit(normalized_question) or 1)
    elif not plan.ordering:
        if group_by is not None:
            plan.ordering = [QueryOrdering(field_name=group_by, direction="asc")]

    return plan, _explain_plan(plan)


def _detect_measures(normalized_question: str) -> list[CanonicalMeasure]:
    matches: list[CanonicalMeasure] = []
    for measure, aliases in MEASURE_TOKEN_MAP.items():
        if any(_matches_keyword(normalized_question, alias) for alias in aliases):
            matches.append(measure)
    return matches


def _detect_grouping(normalized_question: str) -> QueryDimensionField | None:
    for dimension, aliases in GROUPING_KEYWORDS.items():
        if any(_matches_keyword(normalized_question, alias) for alias in aliases):
            return dimension
    return None


def _detect_aggregation_function(normalized_question: str) -> str | None:
    if _contains_any(normalized_question, AVERAGE_KEYWORDS):
        return "avg"
    if _contains_any(normalized_question, COUNT_KEYWORDS):
        return "count"
    return None


def _detect_ordering(normalized_question: str) -> list[QueryOrdering]:
    if _contains_any(normalized_question, TOP_KEYWORDS):
        return [QueryOrdering(field_name="metric_value", direction="desc")]
    if _contains_any(normalized_question, LOW_KEYWORDS):
        return [QueryOrdering(field_name="metric_value", direction="asc")]
    return []


def _detect_filters(normalized_question: str, metadata: dict[str, Any]) -> list[QueryFilter]:
    filters: list[QueryFilter] = []
    dimension_metadata = {
        "variety": metadata.get("available_varieties", []),
        "location": metadata.get("available_locations", []),
        "treatment": metadata.get("available_treatments", []),
        "plot_id": metadata.get("available_plot_ids", []),
    }
    for field_name, values in dimension_metadata.items():
        matched_value = _match_available_value(normalized_question, values)
        if matched_value is None:
            continue
        filters.append(
            QueryFilter(
                field_name=field_name,
                operator="eq",
                value=matched_value,
                source_text=str(matched_value),
            )
        )
    return filters


def _detect_date_filters(normalized_question: str) -> list[QueryFilter]:
    filters: list[QueryFilter] = []
    exact_dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", normalized_question)
    if exact_dates:
        exact_date = DateValue.fromisoformat(exact_dates[0])
        filters.extend(
            [
                QueryFilter(field_name="observation_date", operator="gte", value=exact_date.isoformat()),
                QueryFilter(field_name="observation_date", operator="lte", value=exact_date.isoformat()),
            ]
        )
        return filters

    year_matches = re.findall(r"\b(20\d{2})\b", normalized_question)
    if year_matches:
        year = int(year_matches[0])
        filters.extend(
            [
                QueryFilter(field_name="observation_date", operator="gte", value=f"{year}-01-01"),
                QueryFilter(field_name="observation_date", operator="lte", value=f"{year}-12-31"),
            ]
        )
    return filters


def _detect_status_filters(normalized_question: str) -> list[str]:
    statuses: list[str] = []
    if _contains_phrase(normalized_question, VALID_KEYWORDS):
        statuses.append("valid")
    if _contains_phrase(normalized_question, WARNING_KEYWORDS):
        statuses.append("warning")
    if _contains_phrase(normalized_question, INVALID_KEYWORDS):
        statuses.append("invalid")
    return statuses


def _selected_dimensions(
    *,
    group_by: QueryDimensionField | None,
    filters: list[QueryFilter],
) -> list[QueryDimensionField]:
    selected: list[QueryDimensionField] = []
    if group_by is not None:
        selected.append(group_by)
    for filter_item in filters:
        if filter_item.field_name in DIMENSION_TOKEN_MAP:
            selected = _append_if_missing(selected, filter_item.field_name)  # type: ignore[arg-type]
    return selected


def _should_build_record_query(normalized_question: str, plan: QueryPlan) -> bool:
    if _contains_any(normalized_question, LIST_KEYWORDS):
        return True
    non_derived_filters = [
        item
        for item in plan.filters
        if item.field_name not in {"upload_session_id", "variable", "normalized_unit"}
    ]
    return bool(plan.selected_dimensions or non_derived_filters)


def _is_overly_broad_request(normalized_question: str, plan: QueryPlan) -> bool:
    if any(keyword in normalized_question for keyword in ALL_DATA_KEYWORDS):
        return True
    return (
        plan.intent != "aggregate"
        and not plan.selected_measures
        and not [item for item in plan.filters if item.field_name != "upload_session_id"]
    )


def _has_filter(filters: list[QueryFilter], field_name: str) -> bool:
    return any(item.field_name == field_name for item in filters)


def _resolve_limit(normalized_question: str, limit_override: int | None) -> int:
    if limit_override is not None:
        return min(limit_override, MAX_RECORD_LIMIT)
    extracted = _extract_numeric_limit(normalized_question)
    if extracted is None:
        return DEFAULT_RECORD_LIMIT
    return min(extracted, MAX_RECORD_LIMIT)


def _extract_numeric_limit(normalized_question: str) -> int | None:
    matches = re.findall(r"\b(?:top|first)\s+(\d{1,3})\b", normalized_question)
    if not matches:
        return None
    return int(matches[0])


def _match_available_value(normalized_question: str, values: list[Any]) -> str | None:
    normalized_candidates = sorted(
        [
            (str(value), _normalize_text(str(value)))
            for value in values
            if value is not None
        ],
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for raw_value, normalized_value in normalized_candidates:
        if normalized_value and normalized_value in normalized_question:
            return raw_value
    return None


def _append_if_missing(items: list[Any], value: Any) -> list[Any]:
    if value in items:
        return items
    return [*items, value]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_matches_keyword(text, keyword) for keyword in keywords)


def _contains_phrase(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_matches_keyword(text, keyword) for keyword in keywords)


def _matches_keyword(text: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", text) is not None


def _normalize_text(value: str) -> str:
    lowered = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", lowered.strip())


def _explain_plan(plan: QueryPlan) -> list[str]:
    lines: list[str] = []
    if plan.intent == "select_records":
        lines.append("The query was understood as a bounded record listing over the safe read-only view.")
    elif plan.intent == "aggregate":
        lines.append("The query was understood as a structured aggregation over the safe read-only view.")

    if plan.target_measure is not None:
        lines.append(f"Target measure: {plan.target_measure}.")
    if plan.grouping:
        lines.append(f"Grouping: {', '.join(plan.grouping)}.")
    if plan.filters:
        filter_summary = ", ".join(f"{item.field_name} {item.operator} {item.value}" for item in plan.filters)
        lines.append(f"Applied filters: {filter_summary}.")
    lines.extend(plan.validation_notes)
    return lines

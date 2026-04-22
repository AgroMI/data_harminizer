from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.services.harmonized_query_service import (
    HarmonizedObservationFilters,
    list_harmonized_observations,
)
from backend.app.services.nl_query_service import execute_nl_query
from backend.app.services.retrieval_service import retrieve_query_context
from etl.types import CanonicalMeasure
from etl.unit_harmonization import canonical_unit_for_measure

DEFAULT_ANSWER_CONTEXT_LIMIT = 10
DEFAULT_SCOPE_QUERY_LIMIT = 50
QUERY_RESULT_SOURCE_ID = "query:result"
RAW_CONTEXT_SOURCE_TYPES = (
    "raw_artifact",
    "sheet_manifest",
    "parse_warning",
    "preview_block",
)
SCHEMA_CONTEXT_SOURCE_TYPES = (
    "schema_doc",
    "canonical_catalog",
    "unit_doc",
    "validation_doc",
    "query_metadata",
)


def build_answer_bundle(
    *,
    question: str | None,
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
    include_context: bool,
    include_schema_context: bool,
    include_raw_context: bool,
) -> dict[str, Any]:
    query_response = _run_query_layer(
        question=question,
        upload_session_id=upload_session_id,
        variable=variable,
    )
    resolved_question = str(query_response["question"])

    context_response = _empty_context_response()
    if include_context:
        context_response = retrieve_query_context(
            upload_session_id=upload_session_id,
            variable=_resolved_variable(query_response=query_response, requested_variable=variable),
            question=resolved_question if question else None,
            include_schema_context=include_schema_context,
            include_raw_context=include_raw_context,
            limit=DEFAULT_ANSWER_CONTEXT_LIMIT,
        )

    sources = _build_answer_sources(
        query_response=query_response,
        context_documents=context_response["context_documents"],
    )
    key_findings = _build_key_findings(
        query_response=query_response,
        sources=sources,
    )
    quality_notes = _build_quality_notes(
        query_response=query_response,
        sources=sources,
    )
    answer_summary = _build_answer_summary(
        query_response=query_response,
        key_findings=key_findings,
        quality_notes=quality_notes,
        context_count=len(context_response["context_documents"]),
    )
    answer_sections = _build_answer_sections(
        query_response=query_response,
        context_response=context_response,
        sources=sources,
        answer_summary=answer_summary,
        quality_notes=quality_notes,
    )

    return {
        "question": resolved_question,
        "supported": query_response["supported"],
        "recognized_intent": query_response["recognized_intent"],
        "query_plan": query_response["query_plan"],
        "result_type": query_response["result_type"],
        "results": query_response["results"],
        "answer_summary": answer_summary,
        "answer_sections": answer_sections,
        "key_findings": key_findings,
        "quality_notes": quality_notes,
        "context_documents": context_response["context_documents"],
        "sources": sources,
        "query_metadata_snapshot": context_response["query_metadata_snapshot"],
    }


def _run_query_layer(
    *,
    question: str | None,
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
) -> dict[str, Any]:
    if question:
        return execute_nl_query(
            question=question,
            upload_session_id=upload_session_id,
            variable=variable,
        )
    return _build_scope_query_response(
        upload_session_id=upload_session_id,
        variable=variable,
    )


def _build_scope_query_response(
    *,
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
) -> dict[str, Any]:
    plan = _build_scope_query_plan(
        upload_session_id=upload_session_id,
        variable=variable,
    )
    response = list_harmonized_observations(
        limit=DEFAULT_SCOPE_QUERY_LIMIT,
        filters=HarmonizedObservationFilters(
            upload_session_id=upload_session_id,
            variable=variable,
            normalized_unit=canonical_unit_for_measure(variable) if variable else None,
        ),
    )
    question = _build_scope_question(
        upload_session_id=upload_session_id,
        variable=variable,
    )
    return {
        "question": question,
        "supported": True,
        "recognized_intent": plan["intent_type"],
        "query_plan": plan,
        "result_type": "records",
        "results": {
            "records": response["items"],
            "aggregations": [],
            "top_group": None,
            "count": response["count"],
        },
        "explanation": _build_scope_explanation(plan),
    }


def _build_scope_query_plan(
    *,
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
) -> dict[str, Any]:
    return {
        "intent_type": "list_records",
        "variable": variable,
        "group_by": None,
        "metric": None,
        "filters": {
            "upload_session_id": upload_session_id,
            "variable": variable,
            "variety": None,
            "location": None,
            "treatment": None,
            "plot_id": None,
            "observation_date_from": None,
            "observation_date_to": None,
            "validation_status": None,
            "validation_statuses": [],
            "quality_flag": None,
            "normalized_unit": canonical_unit_for_measure(variable) if variable else None,
        },
        "include_invalid": False,
        "limit": DEFAULT_SCOPE_QUERY_LIMIT,
        "top_k": None,
    }


def _build_scope_question(
    *,
    upload_session_id: str | None,
    variable: CanonicalMeasure | None,
) -> str:
    scope_parts: list[str] = []
    if variable:
        scope_parts.append(f"variable={variable}")
    if upload_session_id:
        scope_parts.append(f"upload_session_id={upload_session_id}")
    return "Direct answer scope: " + ", ".join(scope_parts)


def _build_scope_explanation(plan: dict[str, Any]) -> str:
    filters = plan["filters"]
    active_filters = [
        f"{key}={value}"
        for key in ("upload_session_id", "variable", "normalized_unit")
        if (value := filters.get(key))
    ]
    return "Built a direct read-only answer from explicit query scope: " + ", ".join(active_filters) + "."


def _resolved_variable(
    *,
    query_response: dict[str, Any],
    requested_variable: CanonicalMeasure | None,
) -> CanonicalMeasure | None:
    plan = query_response.get("query_plan") or {}
    return plan.get("variable") or requested_variable


def _empty_context_response() -> dict[str, Any]:
    return {
        "summary": "",
        "context_documents": [],
        "sources": [],
        "explanation_sections": [],
        "query_metadata_snapshot": None,
    }


def _build_answer_sources(
    *,
    query_response: dict[str, Any],
    context_documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sources = [_build_query_result_source(query_response=query_response)]
    sources.extend(_build_context_sources(context_documents))
    return sources


def _build_query_result_source(*, query_response: dict[str, Any]) -> dict[str, Any]:
    plan = query_response["query_plan"]
    results = query_response["results"]
    return {
        "source_id": QUERY_RESULT_SOURCE_ID,
        "document_id": "query-result",
        "source_type": "query_result",
        "title": "Harmonized query result",
        "snippet": _build_query_result_snippet(query_response=query_response),
        "metadata": {
            "recognized_intent": query_response["recognized_intent"],
            "result_type": query_response["result_type"],
            "record_count": results.get("count", 0),
            "variable": plan.get("variable"),
            "group_by": plan.get("group_by"),
            "metric": plan.get("metric"),
            "include_invalid": plan.get("include_invalid"),
        },
        "upload_session_id": plan["filters"].get("upload_session_id"),
    }


def _build_query_result_snippet(*, query_response: dict[str, Any]) -> str:
    plan = query_response["query_plan"]
    result_type = query_response["result_type"]
    count = query_response["results"].get("count", 0)
    if not query_response["supported"]:
        return str(query_response.get("explanation") or "Unsupported read-only query.")

    if result_type == "aggregation":
        return (
            f"Aggregation over variable={plan.get('variable')} grouped by {plan.get('group_by')} "
            f"returned {count} groups."
        )
    if result_type == "top_group":
        top_group = query_response["results"].get("top_group")
        return (
            f"Top group query over variable={plan.get('variable')} grouped by {plan.get('group_by')} "
            f"returned {_display_text(top_group.get('group_value') if top_group else None)}."
        )
    return f"Record query returned {count} harmonized rows."


def _build_context_sources(context_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": f"context:{document['document_id']}",
            "document_id": document["document_id"],
            "source_type": document["source_type"],
            "title": document["title"],
            "snippet": document["snippet"],
            "metadata": document["metadata"],
            "upload_session_id": document["upload_session_id"],
        }
        for document in context_documents
    ]


def _build_key_findings(
    *,
    query_response: dict[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_type = query_response["result_type"]
    results = query_response["results"]
    plan = query_response["query_plan"]
    findings: list[dict[str, Any]] = []

    if not query_response["supported"]:
        return [
            {
                "finding_id": "support_status",
                "label": "Support status",
                "statement": "The question is outside the supported read-only NL-query patterns.",
                "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
            }
        ]

    if result_type == "top_group":
        top_group = results.get("top_group")
        if top_group is None:
            return findings
        findings.append(
            {
                "finding_id": "top_group",
                "label": "Top group",
                "statement": (
                    f"{_display_text(top_group.get('group_value'))} is the highest {plan['group_by']} for "
                    f"average normalized {plan['variable']} at "
                    f"{_format_metric_value(top_group.get('metric_value'), top_group.get('normalized_unit'))}."
                ),
                "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
            }
        )
        findings.append(
            {
                "finding_id": "top_group_record_count",
                "label": "Supporting records",
                "statement": f"The returned top group is based on {top_group.get('record_count')} records.",
                "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
            }
        )
        return findings

    if result_type == "aggregation":
        aggregations = list(results.get("aggregations") or [])
        findings.append(
            {
                "finding_id": "aggregation_group_count",
                "label": "Aggregation groups",
                "statement": (
                    f"The query returned {len(aggregations)} {plan['group_by']} groups for average normalized "
                    f"{plan['variable']}."
                ),
                "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
            }
        )
        top_group = _pick_highest_group(aggregations)
        if top_group is not None:
            findings.append(
                {
                    "finding_id": "highest_group",
                    "label": "Highest group",
                    "statement": (
                        f"The highest group is {_display_text(top_group.get('group_value'))} at "
                        f"{_format_metric_value(top_group.get('metric_value'), top_group.get('normalized_unit'))}."
                    ),
                    "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
                }
            )
        return findings

    records = list(results.get("records") or [])
    findings.append(
        {
            "finding_id": "record_count",
            "label": "Record count",
            "statement": f"The query returned {results.get('count', len(records))} harmonized records.",
            "evidence_source_ids": [QUERY_RESULT_SOURCE_ID],
        }
    )

    status_counts = _validation_status_counts(records)
    problematic_counts = {key: value for key, value in status_counts.items() if key in {"warning", "invalid"} and value > 0}
    if problematic_counts:
        findings.append(
            {
                "finding_id": "status_mix",
                "label": "Validation status mix",
                "statement": "Returned records include " + _format_counter(problematic_counts) + ".",
                "evidence_source_ids": _combine_source_ids(
                    [QUERY_RESULT_SOURCE_ID],
                    _source_ids_for_types(sources, {"validation_doc"}),
                ),
            }
        )

    flag_counts = _quality_flag_counts(records)
    if flag_counts:
        findings.append(
            {
                "finding_id": "quality_flags",
                "label": "Observed quality flags",
                "statement": "Observed quality flags: " + _format_counter(flag_counts) + ".",
                "evidence_source_ids": _combine_source_ids(
                    [QUERY_RESULT_SOURCE_ID],
                    _source_ids_for_types(sources, {"validation_doc"}),
                ),
            }
        )

    return findings


def _build_quality_notes(
    *,
    query_response: dict[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not query_response["supported"]:
        return []

    notes: list[dict[str, Any]] = []
    validation_source_ids = _source_ids_for_types(sources, {"validation_doc"})
    query_validation_sources = _combine_source_ids([QUERY_RESULT_SOURCE_ID], validation_source_ids)
    result_type = query_response["result_type"]
    plan = query_response["query_plan"]
    results = query_response["results"]

    if result_type in {"aggregation", "top_group"}:
        if plan.get("include_invalid"):
            notes.append(
                {
                    "note_id": "aggregation_scope",
                    "level": "warning",
                    "text": "Invalid harmonized rows are included in this aggregation scope.",
                    "source_ids": query_validation_sources,
                }
            )
        else:
            notes.append(
                {
                    "note_id": "aggregation_scope",
                    "level": "info",
                    "text": "Invalid harmonized rows are excluded from this aggregation scope.",
                    "source_ids": query_validation_sources,
                }
            )
        return notes

    records = list(results.get("records") or [])
    status_counts = _validation_status_counts(records)
    problematic_counts = {key: value for key, value in status_counts.items() if key in {"warning", "invalid"} and value > 0}
    if problematic_counts:
        notes.append(
            {
                "note_id": "validation_status",
                "level": "warning",
                "text": "Returned records include " + _format_counter(problematic_counts) + ".",
                "source_ids": query_validation_sources,
            }
        )
    else:
        notes.append(
            {
                "note_id": "validation_status",
                "level": "info",
                "text": "Returned records are valid in the current answer slice.",
                "source_ids": query_validation_sources or [QUERY_RESULT_SOURCE_ID],
            }
        )

    flag_counts = _quality_flag_counts(records)
    if flag_counts:
        notes.append(
            {
                "note_id": "quality_flags",
                "level": "warning",
                "text": "Observed quality flags: " + _format_counter(flag_counts) + ".",
                "source_ids": query_validation_sources,
            }
        )

    return notes


def _build_answer_summary(
    *,
    query_response: dict[str, Any],
    key_findings: list[dict[str, Any]],
    quality_notes: list[dict[str, Any]],
    context_count: int,
) -> str:
    if not query_response["supported"]:
        parts = [
            "The request is outside the supported read-only query patterns, so no harmonized query result was produced.",
        ]
        if context_count > 0:
            parts.append(f"Linked context documents: {context_count}.")
        return _join_sentences(parts)

    result_type = query_response["result_type"]
    parts: list[str] = []
    if result_type == "top_group":
        parts.extend(_finding_statements(key_findings, limit=2))
    elif result_type == "aggregation":
        parts.extend(_finding_statements(key_findings, limit=2))
    else:
        parts.extend(_finding_statements(key_findings, limit=1))

    summary_note = _preferred_summary_note(quality_notes)
    if summary_note:
        parts.append(summary_note["text"])

    if context_count > 0:
        parts.append(f"Linked context documents: {context_count}.")

    return _join_sentences(parts)


def _build_answer_sections(
    *,
    query_response: dict[str, Any],
    context_response: dict[str, Any],
    sources: list[dict[str, Any]],
    answer_summary: str,
    quality_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sections = [
        _build_result_overview_section(
            query_response=query_response,
            answer_summary=answer_summary,
        ),
        _build_quality_context_section(
            query_response=query_response,
            sources=sources,
            quality_notes=quality_notes,
        ),
        _build_source_context_section(
            context_response=context_response,
            sources=sources,
        ),
    ]

    limitations_section = _build_limitations_section(
        query_response=query_response,
        context_response=context_response,
    )
    if limitations_section is not None:
        sections.append(limitations_section)

    return sections


def _build_result_overview_section(
    *,
    query_response: dict[str, Any],
    answer_summary: str,
) -> dict[str, Any]:
    return {
        "section_id": "result_overview",
        "section_type": "result_overview",
        "title": "Result overview",
        "body": _join_sentences(
            [
                str(query_response.get("explanation") or ""),
                answer_summary,
            ]
        ),
        "source_ids": [QUERY_RESULT_SOURCE_ID],
    }


def _build_quality_context_section(
    *,
    query_response: dict[str, Any],
    sources: list[dict[str, Any]],
    quality_notes: list[dict[str, Any]],
) -> dict[str, Any]:
    source_ids = _combine_source_ids(
        [QUERY_RESULT_SOURCE_ID],
        _source_ids_for_types(sources, {"validation_doc"}),
    )
    if quality_notes:
        body = _join_sentences(note["text"] for note in quality_notes)
    elif query_response["supported"]:
        body = "No additional quality note was required for the current answer slice."
    else:
        body = "Quality context is unavailable because no supported harmonized query result was produced."

    return {
        "section_id": "quality_context",
        "section_type": "quality_context",
        "title": "Quality context",
        "body": body,
        "source_ids": source_ids,
    }


def _build_source_context_section(
    *,
    context_response: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    context_documents = context_response["context_documents"]
    context_source_ids = _source_ids_for_types(
        sources,
        set(RAW_CONTEXT_SOURCE_TYPES + SCHEMA_CONTEXT_SOURCE_TYPES),
    )

    if not context_documents:
        return {
            "section_id": "source_context",
            "section_type": "source_context",
            "title": "Source context",
            "body": "No linked retrieval context documents were included in this answer bundle.",
            "source_ids": [],
        }

    upload_ids = sorted(
        {
            str(document["upload_session_id"])
            for document in context_documents
            if document.get("upload_session_id")
        }
    )
    raw_counts = Counter(
        str(document["source_type"])
        for document in context_documents
        if str(document["source_type"]) in RAW_CONTEXT_SOURCE_TYPES
    )
    schema_counts = Counter(
        str(document["source_type"])
        for document in context_documents
        if str(document["source_type"]) in SCHEMA_CONTEXT_SOURCE_TYPES
    )

    parts: list[str] = []
    if upload_ids:
        parts.append("Context is linked to " + ", ".join(f"upload_session_id={item}" for item in upload_ids) + ".")
    else:
        parts.append("No upload-linked provenance context was attached.")

    if raw_counts:
        parts.append("Raw/provenance context includes " + _format_counter(raw_counts) + ".")
    if schema_counts:
        parts.append("Schema/system context includes " + _format_counter(schema_counts) + ".")
    if raw_counts.get("parse_warning", 0) > 0:
        parts.append(f"Parse warnings were present in {raw_counts['parse_warning']} linked context documents.")

    return {
        "section_id": "source_context",
        "section_type": "source_context",
        "title": "Source context",
        "body": _join_sentences(parts),
        "source_ids": context_source_ids,
    }


def _build_limitations_section(
    *,
    query_response: dict[str, Any],
    context_response: dict[str, Any],
) -> dict[str, Any] | None:
    parts: list[str] = []
    if not query_response["supported"]:
        parts.append(
            "No harmonized query result was produced because the question is outside the supported read-only NL-query patterns."
        )
    if not context_response["context_documents"]:
        parts.append("No linked retrieval context documents were available for this answer.")

    if not parts:
        return None

    return {
        "section_id": "limitations",
        "section_type": "limitations",
        "title": "Limitations",
        "body": _join_sentences(parts),
        "source_ids": [QUERY_RESULT_SOURCE_ID],
    }


def _finding_statements(key_findings: list[dict[str, Any]], *, limit: int) -> list[str]:
    return [item["statement"] for item in key_findings[:limit]]


def _preferred_summary_note(quality_notes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for note in quality_notes:
        if note["level"] == "warning":
            return note
    return quality_notes[0] if quality_notes else None


def _pick_highest_group(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: (float(item["metric_value"]), str(item.get("group_value") or "")))


def _validation_status_counts(records: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(item.get("validation_status") or "unknown") for item in records)


def _quality_flag_counts(records: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        str(flag)
        for item in records
        for flag in list(item.get("quality_flags") or [])
        if flag
    )


def _source_ids_for_types(
    sources: list[dict[str, Any]],
    source_types: set[str],
) -> list[str]:
    return [
        str(source["source_id"])
        for source in sources
        if str(source["source_type"]) in source_types
    ]


def _combine_source_ids(*groups: list[str]) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            combined.append(item)
    return combined


def _format_counter(counts: Counter[str] | dict[str, int]) -> str:
    return ", ".join(
        f"{key}={counts[key]}"
        for key in sorted(counts)
        if counts[key] > 0
    )


def _join_sentences(parts: Any) -> str:
    normalized_parts = [str(part).strip().rstrip(".") for part in parts if str(part).strip()]
    if not normalized_parts:
        return ""
    return ". ".join(normalized_parts) + "."


def _display_text(value: Any, fallback: str = "n/a") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _format_metric_value(value: Any, unit: Any) -> str:
    metric_text = _display_text(value)
    unit_text = _display_text(unit, "")
    if unit_text:
        return f"{metric_text} {unit_text}"
    return metric_text

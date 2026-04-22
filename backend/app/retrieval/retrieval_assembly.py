from __future__ import annotations

from collections import defaultdict

from backend.app.retrieval.retrieval_search import build_snippet, tokenize_retrieval_text
from backend.app.retrieval.retrieval_types import RetrievalDocument


def build_source_summaries(documents: list[RetrievalDocument]) -> list[dict[str, object]]:
    grouped_counts: dict[tuple[str, str | None], int] = defaultdict(int)
    for document in documents:
        grouped_counts[(document.source_type, document.upload_session_id)] += 1

    summaries = [
        {
            "source_type": source_type,
            "document_count": count,
            "upload_session_id": upload_session_id,
        }
        for (source_type, upload_session_id), count in grouped_counts.items()
    ]
    summaries.sort(key=lambda item: (str(item["upload_session_id"] or ""), str(item["source_type"])))
    return summaries


def build_explanation_sections(
    *,
    documents: list[RetrievalDocument],
    variable: str | None,
    question: str | None,
) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    if variable or question:
        scope_parts: list[str] = []
        if variable:
            scope_parts.append(f"canonical variable={variable}")
        if question:
            scope_parts.append(f"question={question}")
        sections.append(
            {
                "title": "Query scope",
                "body": "Context assembled for " + ", ".join(scope_parts) + ".",
                "source_document_ids": [],
            }
        )

    schema_docs = [document for document in documents if document.upload_session_id is None]
    if schema_docs:
        sections.append(
            {
                "title": "Schema context",
                "body": f"Included {len(schema_docs)} schema or system context documents.",
                "source_document_ids": [document.document_id for document in schema_docs],
            }
        )

    raw_docs = [document for document in documents if document.upload_session_id is not None]
    if raw_docs:
        sections.append(
            {
                "title": "Raw provenance context",
                "body": f"Included {len(raw_docs)} upload-linked provenance or preview context documents.",
                "source_document_ids": [document.document_id for document in raw_docs],
            }
        )

    return sections


def build_context_summary(
    *,
    documents: list[RetrievalDocument],
    variable: str | None,
    upload_session_id: str | None,
) -> str:
    source_types = sorted({document.source_type for document in documents})
    scope_parts: list[str] = []
    if variable:
        scope_parts.append(f"variable={variable}")
    if upload_session_id:
        scope_parts.append(f"upload_session_id={upload_session_id}")

    scope_suffix = f" for {', '.join(scope_parts)}" if scope_parts else ""
    source_suffix = ", ".join(source_types) if source_types else "no sources"
    return f"Retrieved {len(documents)} context documents{scope_suffix} from {source_suffix}."


def serialize_document(
    *,
    document: RetrievalDocument,
    query_text: str | None = None,
    score: float | None = None,
) -> dict[str, object]:
    query_tokens = tokenize_retrieval_text(query_text or "")
    snippet = build_snippet(text=document.text, query_tokens=query_tokens) if query_tokens else document.text[:220]
    return {
        "document_id": document.document_id,
        "source_type": document.source_type,
        "title": document.title,
        "text": document.text,
        "snippet": snippet,
        "metadata": dict(document.metadata),
        "upload_session_id": document.upload_session_id,
        "score": score,
    }

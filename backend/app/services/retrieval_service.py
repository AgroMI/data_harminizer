from __future__ import annotations

from backend.app.retrieval.retrieval_assembly import (
    build_context_summary,
    build_explanation_sections,
    build_source_summaries,
    serialize_document,
)
from backend.app.retrieval.retrieval_search import search_documents
from backend.app.retrieval.retrieval_sources import (
    build_raw_context_documents,
    build_schema_documents,
)
from backend.app.retrieval.retrieval_types import RetrievalDocument
from backend.app.services.harmonized_query_service import get_harmonized_query_metadata
from backend.app.services.uploads import get_upload_session


def retrieve_query_context(
    *,
    upload_session_id: str | None,
    variable: str | None,
    question: str | None,
    include_schema_context: bool,
    include_raw_context: bool,
    limit: int,
) -> dict[str, object]:
    query_metadata = get_harmonized_query_metadata() if include_schema_context else None
    documents = _load_documents(
        upload_session_id=upload_session_id,
        include_schema_context=include_schema_context,
        include_raw_context=include_raw_context,
        query_metadata=query_metadata,
    )

    selected_documents = _select_context_documents(
        documents=documents,
        variable=variable,
        question=question,
        include_schema_context=include_schema_context,
        include_raw_context=include_raw_context,
        limit=limit,
    )

    return {
        "summary": build_context_summary(
            documents=selected_documents,
            variable=variable,
            upload_session_id=upload_session_id,
        ),
        "context_documents": [
            serialize_document(document=document, query_text=question or variable)
            for document in selected_documents
        ],
        "sources": build_source_summaries(selected_documents),
        "explanation_sections": build_explanation_sections(
            documents=selected_documents,
            variable=variable,
            question=question,
        ),
        "query_metadata_snapshot": query_metadata,
    }


def search_retrieval_context(
    *,
    query: str,
    upload_session_id: str | None,
    limit: int,
) -> dict[str, object]:
    documents = _load_documents(
        upload_session_id=upload_session_id,
        include_schema_context=True,
        include_raw_context=True,
        query_metadata=get_harmonized_query_metadata(),
    )
    matches = search_documents(query=query, documents=documents, limit=limit)
    return {
        "query": query,
        "count": len(matches),
        "items": [
            serialize_document(
                document=match.document,
                query_text=query,
                score=match.score,
            )
            for match in matches
        ],
    }


def _load_documents(
    *,
    upload_session_id: str | None,
    include_schema_context: bool,
    include_raw_context: bool,
    query_metadata: dict[str, object] | None,
) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    if include_schema_context and query_metadata is not None:
        documents.extend(build_schema_documents(query_metadata))
    if include_raw_context and upload_session_id:
        upload_detail = get_upload_session(upload_session_id)
        documents.extend(build_raw_context_documents(upload_detail))
    return documents


def _select_context_documents(
    *,
    documents: list[RetrievalDocument],
    variable: str | None,
    question: str | None,
    include_schema_context: bool,
    include_raw_context: bool,
    limit: int,
) -> list[RetrievalDocument]:
    selected: list[RetrievalDocument] = []

    if include_schema_context:
        selected.extend(_preferred_schema_documents(documents=documents, variable=variable))
    if include_raw_context:
        selected.extend(_preferred_raw_documents(documents=documents, variable=variable))

    if question:
        question_matches = search_documents(query=question, documents=documents, limit=limit)
        selected.extend(match.document for match in question_matches)

    if variable and len(selected) < limit:
        variable_matches = search_documents(query=variable, documents=documents, limit=limit)
        selected.extend(match.document for match in variable_matches)

    if not selected:
        selected = documents[:limit]

    return _dedupe_documents(selected)[:limit]


def _preferred_schema_documents(
    *,
    documents: list[RetrievalDocument],
    variable: str | None,
) -> list[RetrievalDocument]:
    selected: list[RetrievalDocument] = []
    selected.extend(_documents_by_id(documents, {"schema:overview", "query:metadata", "validation:overview"}))

    if variable:
        selected.extend(
            document
            for document in documents
            if document.upload_session_id is None
            and (
                document.metadata.get("canonical_measure") == variable
                or document.document_id in {f"canonical:measure:{variable}", f"units:{variable}"}
            )
        )

    return _dedupe_documents(selected)


def _preferred_raw_documents(
    *,
    documents: list[RetrievalDocument],
    variable: str | None,
) -> list[RetrievalDocument]:
    raw_documents = [document for document in documents if document.upload_session_id is not None]
    selected: list[RetrievalDocument] = []
    selected.extend(document for document in raw_documents if document.source_type == "raw_artifact")

    if variable:
        selected.extend(
            document
            for document in raw_documents
            if document.source_type == "preview_block"
            and variable in [str(item) for item in document.metadata.get("canonical_measures", [])]
        )
    else:
        selected.extend(document for document in raw_documents if document.source_type == "preview_block")

    selected.extend(document for document in raw_documents if document.source_type == "sheet_manifest")
    selected.extend(document for document in raw_documents if document.source_type == "parse_warning")

    return _dedupe_documents(selected)


def _documents_by_id(documents: list[RetrievalDocument], document_ids: set[str]) -> list[RetrievalDocument]:
    return [document for document in documents if document.document_id in document_ids]


def _dedupe_documents(documents: list[RetrievalDocument]) -> list[RetrievalDocument]:
    deduped: list[RetrievalDocument] = []
    seen_ids: set[str] = set()
    for document in documents:
        if document.document_id in seen_ids:
            continue
        seen_ids.add(document.document_id)
        deduped.append(document)
    return deduped

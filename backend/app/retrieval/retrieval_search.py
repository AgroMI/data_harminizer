from __future__ import annotations

import re
import unicodedata

from backend.app.retrieval.retrieval_types import RetrievalDocument, RetrievalMatch

SNIPPET_LENGTH = 220


def search_documents(
    *,
    query: str,
    documents: list[RetrievalDocument],
    limit: int,
) -> list[RetrievalMatch]:
    normalized_query = normalize_retrieval_text(query)
    query_tokens = tokenize_retrieval_text(normalized_query)
    if not query_tokens:
        return []

    matches: list[RetrievalMatch] = []
    for document in documents:
        score = _score_document(document=document, normalized_query=normalized_query, query_tokens=query_tokens)
        if score <= 0:
            continue
        matches.append(
            RetrievalMatch(
                document=document,
                score=round(score, 4),
                snippet=build_snippet(text=document.text, query_tokens=query_tokens),
            )
        )

    matches.sort(
        key=lambda item: (
            -item.score,
            item.document.source_type,
            item.document.title.casefold(),
            item.document.document_id,
        )
    )
    return matches[:limit]


def build_snippet(*, text: str, query_tokens: set[str]) -> str:
    cleaned_text = " ".join(text.split())
    if not cleaned_text:
        return ""

    lowered = normalize_retrieval_text(cleaned_text)
    first_match_index = min(
        (lowered.find(token) for token in query_tokens if token in lowered),
        default=-1,
    )
    if first_match_index < 0 or len(cleaned_text) <= SNIPPET_LENGTH:
        return cleaned_text[:SNIPPET_LENGTH]

    start = max(first_match_index - 40, 0)
    end = min(start + SNIPPET_LENGTH, len(cleaned_text))
    snippet = cleaned_text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(cleaned_text):
        snippet = f"{snippet}..."
    return snippet


def normalize_retrieval_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    compact = re.sub(r"[^a-z0-9%/._-]+", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def tokenize_retrieval_text(value: str) -> set[str]:
    return {token for token in normalize_retrieval_text(value).split(" ") if len(token) >= 2}


def _score_document(
    *,
    document: RetrievalDocument,
    normalized_query: str,
    query_tokens: set[str],
) -> float:
    title_text = normalize_retrieval_text(document.title)
    body_text = normalize_retrieval_text(document.text)
    metadata_text = normalize_retrieval_text(_metadata_to_text(document.metadata))
    searchable_text = " ".join(part for part in (title_text, body_text, metadata_text) if part)

    exact_phrase_bonus = 25.0 if normalized_query and normalized_query in searchable_text else 0.0
    title_matches = sum(1 for token in query_tokens if token in title_text)
    body_matches = sum(1 for token in query_tokens if token in body_text)
    metadata_matches = sum(1 for token in query_tokens if token in metadata_text)

    return exact_phrase_bonus + title_matches * 5.0 + body_matches * 2.0 + metadata_matches * 1.0


def _metadata_to_text(metadata: dict[str, object]) -> str:
    parts: list[str] = []
    for key, value in metadata.items():
        parts.append(str(key))
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
            continue
        parts.append(str(value))
    return " ".join(parts)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

RetrievalSourceType: TypeAlias = Literal[
    "raw_artifact",
    "sheet_manifest",
    "parse_warning",
    "preview_block",
    "schema_doc",
    "canonical_catalog",
    "unit_doc",
    "validation_doc",
    "query_metadata",
]


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    document_id: str
    source_type: RetrievalSourceType
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    upload_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalMatch:
    document: RetrievalDocument
    score: float
    snippet: str

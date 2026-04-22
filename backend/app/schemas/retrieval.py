from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import RetrievalSourceType
from backend.app.schemas.query import HarmonizedQueryMetadataResponse


class RetrievalContextDocument(BaseModel):
    document_id: str
    source_type: RetrievalSourceType
    title: str
    text: str
    snippet: str
    metadata: dict[str, object] = Field(default_factory=dict)
    upload_session_id: str | None = None
    score: float | None = None


class RetrievalSourceSummaryItem(BaseModel):
    source_type: RetrievalSourceType
    document_count: int = Field(ge=0)
    upload_session_id: str | None = None


class RetrievalExplanationSection(BaseModel):
    title: str
    body: str
    source_document_ids: list[str] = Field(default_factory=list)


class RetrievalContextResponse(BaseModel):
    summary: str
    context_documents: list[RetrievalContextDocument] = Field(default_factory=list)
    sources: list[RetrievalSourceSummaryItem] = Field(default_factory=list)
    explanation_sections: list[RetrievalExplanationSection] = Field(default_factory=list)
    query_metadata_snapshot: HarmonizedQueryMetadataResponse | None = None


class RetrievalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    upload_session_id: str | None = None
    limit: int = Field(default=8, ge=1, le=25)


class RetrievalSearchResponse(BaseModel):
    query: str
    count: int = Field(ge=0)
    items: list[RetrievalContextDocument] = Field(default_factory=list)

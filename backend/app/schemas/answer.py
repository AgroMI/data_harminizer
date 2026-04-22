from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.nl_query import (
    NLQueryPlan,
    NLQueryResultPayload,
)
from backend.app.schemas.query import HarmonizedQueryMetadataResponse
from backend.app.schemas.retrieval import (
    RetrievalContextDocument,
)
from backend.app.schemas.common import NLQueryIntentType, NLQueryResultType, RetrievalSourceType
from etl.types import CanonicalMeasure

AnswerSourceType = Literal["query_result"] | RetrievalSourceType
AnswerSectionType = Literal["result_overview", "quality_context", "source_context", "limitations"]
AnswerNoteLevel = Literal["info", "warning"]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, min_length=1, max_length=500)
    upload_session_id: str | None = None
    variable: CanonicalMeasure | None = None
    include_context: bool = True
    include_schema_context: bool = True
    include_raw_context: bool = True

    @model_validator(mode="after")
    def validate_request_scope(self) -> "AnswerRequest":
        if self.question or self.upload_session_id or self.variable:
            return self
        raise ValueError("question, upload_session_id or variable is required.")


class AnswerSourceItem(BaseModel):
    source_id: str
    document_id: str
    source_type: AnswerSourceType
    title: str
    snippet: str
    metadata: dict[str, object] = Field(default_factory=dict)
    upload_session_id: str | None = None


class AnswerSection(BaseModel):
    section_id: str
    section_type: AnswerSectionType
    title: str
    body: str
    source_ids: list[str] = Field(default_factory=list)


class AnswerKeyFinding(BaseModel):
    finding_id: str
    label: str
    statement: str
    evidence_source_ids: list[str] = Field(default_factory=list)


class AnswerQualityNote(BaseModel):
    note_id: str
    level: AnswerNoteLevel
    text: str
    source_ids: list[str] = Field(default_factory=list)


class AnswerResponse(BaseModel):
    question: str
    supported: bool
    recognized_intent: NLQueryIntentType
    query_plan: NLQueryPlan
    result_type: NLQueryResultType
    results: NLQueryResultPayload
    answer_summary: str
    answer_sections: list[AnswerSection] = Field(default_factory=list)
    key_findings: list[AnswerKeyFinding] = Field(default_factory=list)
    quality_notes: list[AnswerQualityNote] = Field(default_factory=list)
    context_documents: list[RetrievalContextDocument] = Field(default_factory=list)
    sources: list[AnswerSourceItem] = Field(default_factory=list)
    query_metadata_snapshot: HarmonizedQueryMetadataResponse | None = None

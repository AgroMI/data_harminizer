from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.services.retrieval_service import (
    retrieve_query_context,
    search_retrieval_context,
)
from backend.app.tools.tool_types import BaseTool
from etl.types import CanonicalMeasure

RetrievalToolOperation = Literal["context", "search"]


class RetrievalToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: RetrievalToolOperation = Field(description="Retrieval operation to execute.")
    upload_session_id: str | None = Field(default=None, description="Optional upload/session scope.")
    variable: CanonicalMeasure | None = Field(default=None, description="Canonical variable for context retrieval.")
    question: str | None = Field(default=None, description="Optional natural language query context.")
    query: str | None = Field(default=None, description="Direct retrieval search query.")
    include_schema_context: bool = Field(default=True, description="Whether schema/query metadata documents may be returned.")
    include_raw_context: bool = Field(default=True, description="Whether raw/provenance documents may be returned.")
    limit: int = Field(default=8, ge=1, le=25, description="Maximum returned documents.")

    @model_validator(mode="after")
    def validate_operation_specific_fields(self) -> "RetrievalToolArguments":
        if self.operation == "search" and not self.query:
            raise ValueError("query is required for search operation.")
        return self


class RetrievalTool(BaseTool):
    tool_name = "retrieval_tool"
    description = "Read-only retrieval over schema, provenance and preview context documents."
    category = "retrieval"
    input_model = RetrievalToolArguments

    def execute(self, arguments: RetrievalToolArguments) -> dict[str, object]:
        if arguments.operation == "search":
            return search_retrieval_context(
                query=arguments.query or "",
                upload_session_id=arguments.upload_session_id,
                limit=arguments.limit,
            )

        return retrieve_query_context(
            upload_session_id=arguments.upload_session_id,
            variable=arguments.variable,
            question=arguments.question,
            include_schema_context=arguments.include_schema_context,
            include_raw_context=arguments.include_raw_context,
            limit=arguments.limit,
        )

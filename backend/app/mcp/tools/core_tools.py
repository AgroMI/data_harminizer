from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.mcp.errors import MCPError
from backend.app.mcp.tool_types import BaseMCPTool, ToolExecutionContext
from backend.app.retrieval.retrieval_search import search_documents
from backend.app.retrieval.retrieval_sources import build_schema_documents
from backend.app.llm.types import PipelineMode
from backend.app.llm.planner_adapter import plan_question_with_optional_llm
from backend.app.services.harmonized_query_service import get_harmonized_query_metadata
from backend.app.services.retrieval_service import search_retrieval_context
from backend.app.text_to_sql.catalog import build_schema_snapshot
from backend.app.text_to_sql.models import (
    GeneratedSql,
    QueryPlan,
    SqlExecutionResult,
    SqlValidationResult,
)
from backend.app.text_to_sql.planner import plan_question
from backend.app.text_to_sql.sql_executor import execute_generated_sql
from backend.app.text_to_sql.sql_generator import generate_sql_from_plan
from backend.app.text_to_sql.sql_validator import validate_generated_sql


class DescribeSchemaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_live_metadata: bool = True


class DescribeSchemaOutput(BaseModel):
    schema_snapshot: dict[str, Any] = Field(default_factory=dict)


class PlanQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    upload_session_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=200)
    explain: bool = True
    mode: PipelineMode = "deterministic"


class PlanQueryOutput(BaseModel):
    query_plan: QueryPlan
    explanation: list[str] = Field(default_factory=list)
    planning_metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateSqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_plan: QueryPlan


class ValidateSqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1)
    parameters: list[object] = Field(default_factory=list)
    query_plan: QueryPlan | None = None


class ValidateSqlOutput(BaseModel):
    validation: SqlValidationResult


class ExecuteSqlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1)
    parameters: list[object] = Field(default_factory=list)
    query_plan: QueryPlan


class ExecuteSqlOutput(BaseModel):
    validation: SqlValidationResult
    execution: SqlExecutionResult


class ExplainMetadataInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str | None = None
    query: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class ExplainMetadataOutput(BaseModel):
    count: int = Field(ge=0)
    items: list[dict[str, Any]] = Field(default_factory=list)


class RetrieveEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    upload_session_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class RetrieveEvidenceOutput(BaseModel):
    query: str
    count: int = Field(ge=0)
    items: list[dict[str, Any]] = Field(default_factory=list)


class DescribeSchemaTool(BaseMCPTool):
    tool_name = "describe_schema"
    description = "Describe the safe read-only schema, canonical fields, dimensions and measures."
    category = "schema"
    input_model = DescribeSchemaInput
    output_model = DescribeSchemaOutput

    def execute(self, arguments: DescribeSchemaInput, context: ToolExecutionContext) -> dict[str, Any]:
        query_metadata = get_harmonized_query_metadata() if arguments.include_live_metadata else {}
        return {
            "schema_snapshot": build_schema_snapshot(query_metadata),
        }


class PlanQueryTool(BaseMCPTool):
    tool_name = "plan_query"
    description = "Convert a natural language request into an explicit, auditable query plan."
    category = "planning"
    input_model = PlanQueryInput
    output_model = PlanQueryOutput

    def execute(self, arguments: PlanQueryInput, context: ToolExecutionContext) -> dict[str, Any]:
        query_plan, explanation, planning_metadata = plan_question_with_optional_llm(
            question=arguments.question,
            upload_session_id=arguments.upload_session_id,
            limit_override=arguments.limit,
            mode=arguments.mode,
            correlation_id=context.correlation_id,
        )
        return {
            "query_plan": query_plan.model_dump(mode="json"),
            "explanation": explanation if arguments.explain else [],
            "planning_metadata": planning_metadata.model_dump(mode="json"),
        }


class GenerateSqlTool(BaseMCPTool):
    tool_name = "generate_sql"
    description = "Generate parameterized SQL exclusively from an approved query plan."
    category = "sql"
    input_model = GenerateSqlInput
    output_model = GeneratedSql

    def execute(self, arguments: GenerateSqlInput, context: ToolExecutionContext) -> dict[str, Any]:
        sql_bundle = generate_sql_from_plan(arguments.query_plan)
        return sql_bundle.model_dump(mode="json")


class ValidateSqlTool(BaseMCPTool):
    tool_name = "validate_sql"
    description = "Statically validate parameterized SQL against the safe read-only SQL subset."
    category = "sql"
    input_model = ValidateSqlInput
    output_model = ValidateSqlOutput

    def execute(self, arguments: ValidateSqlInput, context: ToolExecutionContext) -> dict[str, Any]:
        validation = validate_generated_sql(
            sql_bundle=GeneratedSql(
                sql=arguments.sql,
                parameters=arguments.parameters,
                relation_names=["safe.harmonized_observations_v1"],
                projected_columns=[],
            ),
            plan=arguments.query_plan,
        )
        return {
            "validation": validation.model_dump(mode="json"),
        }


class ExecuteSqlTool(BaseMCPTool):
    tool_name = "execute_sql"
    description = "Execute validated SQL inside a read-only, timeout-limited safe execution context."
    category = "sql"
    input_model = ExecuteSqlInput
    output_model = ExecuteSqlOutput

    def execute(self, arguments: ExecuteSqlInput, context: ToolExecutionContext) -> dict[str, Any]:
        sql_bundle = GeneratedSql(
            sql=arguments.sql,
            parameters=arguments.parameters,
            relation_names=["safe.harmonized_observations_v1"],
            projected_columns=[],
        )
        validation = validate_generated_sql(sql_bundle=sql_bundle, plan=arguments.query_plan)
        if not validation.valid:
            raise MCPError(
                code="sql_validation_failed",
                message="SQL failed static validation and was not executed.",
                details=validation.model_dump(mode="json"),
            )
        execution = execute_generated_sql(sql_bundle=sql_bundle)
        return {
            "validation": validation.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
        }


class ExplainMetadataTool(BaseMCPTool):
    tool_name = "explain_metadata"
    description = "Explain canonical dimensions, measures, units and quality metadata from the schema corpus."
    category = "metadata"
    input_model = ExplainMetadataInput
    output_model = ExplainMetadataOutput

    def execute(self, arguments: ExplainMetadataInput, context: ToolExecutionContext) -> dict[str, Any]:
        query_metadata = get_harmonized_query_metadata()
        documents = build_schema_documents(query_metadata)
        query_text = arguments.query or arguments.topic or "schema overview"
        matches = search_documents(query=query_text, documents=documents, limit=arguments.limit)
        items = [
            {
                "document_id": match.document.document_id,
                "source_type": match.document.source_type,
                "title": match.document.title,
                "text": match.document.text,
                "metadata": match.document.metadata,
                "score": round(match.score, 4),
            }
            for match in matches
        ]
        return {"count": len(items), "items": items}


class RetrieveEvidenceTool(BaseMCPTool):
    tool_name = "retrieve_evidence"
    description = "Retrieve evidence from schema, provenance and validation documents for an answer trace."
    category = "retrieval"
    input_model = RetrieveEvidenceInput
    output_model = RetrieveEvidenceOutput

    def execute(self, arguments: RetrieveEvidenceInput, context: ToolExecutionContext) -> dict[str, Any]:
        result = search_retrieval_context(
            query=arguments.query,
            upload_session_id=arguments.upload_session_id,
            limit=arguments.limit,
        )
        return {
            "query": arguments.query,
            "count": int(result["count"]),
            "items": list(result["items"]),
        }

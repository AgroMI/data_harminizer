from __future__ import annotations

import os
from datetime import date as DateValue

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.app.evaluation.text_to_sql_benchmark_runner import run_text_to_sql_benchmark
from backend.app.llm import LLMAuditListResponse, build_llm_audit_list_response
from backend.app.mcp import (
    MCPAuditListResponse,
    MCPInvokeRequest,
    MCPInvokeResponse,
    MCPToolsListResponse,
    default_mcp_server,
)
from backend.app.mcp.audit import build_audit_list_response
from backend.app.schemas import (
    CommitResponse,
    EditRequest,
    AnswerRequest,
    AnswerResponse,
    HarmonizedAggregationResponse,
    HarmonizedObservationListResponse,
    HarmonizedQueryMetadataResponse,
    HealthResponse,
    NLQueryRequest,
    NLQueryResponse,
    RetrievalContextResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolsListResponse,
    ToolDefinitionResponse,
    UploadCreateResponse,
    UploadDetailResponse,
    UploadPreviewResponse,
    AggregationGroupBy,
    AggregationMetric,
)
from backend.app.services.answer_assembly_service import build_answer_bundle
from backend.app.services.harmonized_query_service import (
    HarmonizedObservationFilters,
    aggregate_harmonized_observations,
    get_harmonized_query_metadata,
    list_harmonized_observations as list_harmonized_query_observations,
)
from backend.app.services.nl_query_service import execute_nl_query
from backend.app.services.retrieval_service import (
    retrieve_query_context,
    search_retrieval_context,
)
from backend.app.tools.tool_registry import default_tool_registry
from backend.app.tools.tool_runner import execute_tool
from backend.app.text_to_sql.models import (
    TextToSqlPipelineRequest,
    TextToSqlPipelineResponse,
)
from backend.app.text_to_sql.service import run_text_to_sql_pipeline
from backend.app.services.uploads import (
    ColumnEditInput,
    apply_preview_edits,
    commit_upload_session,
    create_upload_session,
    get_upload_session,
    get_upload_preview,
)
from etl.types import CanonicalMeasure, CanonicalUnit, QualityFlag, ValidationStatus

app = FastAPI(title="Thesis Warehouse API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/uploads", response_model=UploadCreateResponse)
async def create_upload(file: UploadFile = File(...)) -> UploadCreateResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Received an empty file body — make sure the file was fully written before uploading.")

    filename = file.filename or "upload.xlsx"
    response = create_upload_session(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=file.content_type or "application/octet-stream",
    )
    return UploadCreateResponse.model_validate(response)


@app.get("/uploads/{upload_id}", response_model=UploadDetailResponse)
def read_upload(upload_id: str) -> UploadDetailResponse:
    response = get_upload_session(upload_id)
    return UploadDetailResponse.model_validate(response)


@app.get("/uploads/{upload_id}/preview", response_model=UploadPreviewResponse)
def read_upload_preview(upload_id: str) -> UploadPreviewResponse:
    response = get_upload_preview(upload_id)
    return UploadPreviewResponse.model_validate(response)


@app.post("/uploads/{upload_id}/edits", response_model=UploadPreviewResponse)
def update_preview_edits(upload_id: str, payload: EditRequest) -> UploadPreviewResponse:
    edits = [
        ColumnEditInput(
            block_id=item.block_id,
            column=item.column,
            type_override=item.type_override,
            semantic_role=item.semantic_role,
            canonical_measure=item.canonical_measure,
            canonical_dimension=item.canonical_dimension,
            unit=item.unit,
        )
        for item in payload.columns
    ]
    response = apply_preview_edits(upload_id, edits)
    return UploadPreviewResponse.model_validate(response)


@app.post("/uploads/{upload_id}/commit", response_model=CommitResponse)
def commit_upload(upload_id: str) -> CommitResponse:
    result = commit_upload_session(upload_id)
    return CommitResponse(
        id=result.id,
        status=result.status,
        staging_rows=result.staging_rows,
        harmonized_rows=result.harmonized_rows,
    )

@app.get("/api/harmonized/observations", response_model=HarmonizedObservationListResponse)
def list_harmonized_query_observations_endpoint(
    limit: int = Query(default=100, ge=1, le=1000),
    upload_session_id: str | None = None,
    variable: CanonicalMeasure | None = None,
    variety: str | None = None,
    location: str | None = None,
    treatment: str | None = None,
    plot_id: str | None = None,
    observation_date_from: DateValue | None = None,
    observation_date_to: DateValue | None = None,
    validation_status: ValidationStatus | None = None,
    quality_flag: QualityFlag | None = None,
    normalized_unit: CanonicalUnit | None = None,
) -> HarmonizedObservationListResponse:
    response = list_harmonized_query_observations(
        limit=limit,
        filters=HarmonizedObservationFilters(
            upload_session_id=upload_session_id,
            variable=variable,
            variety=variety,
            location=location,
            treatment=treatment,
            plot_id=plot_id,
            observation_date_from=observation_date_from,
            observation_date_to=observation_date_to,
            validation_status=validation_status,
            quality_flag=quality_flag,
            normalized_unit=normalized_unit,
        ),
    )
    return HarmonizedObservationListResponse.model_validate(response)


@app.get("/api/harmonized/aggregations", response_model=HarmonizedAggregationResponse)
def list_harmonized_aggregations_endpoint(
    group_by: AggregationGroupBy,
    metric: AggregationMetric,
    upload_session_id: str | None = None,
    variable: CanonicalMeasure | None = None,
    variety: str | None = None,
    location: str | None = None,
    treatment: str | None = None,
    plot_id: str | None = None,
    observation_date_from: DateValue | None = None,
    observation_date_to: DateValue | None = None,
    validation_status: ValidationStatus | None = None,
    quality_flag: QualityFlag | None = None,
    normalized_unit: CanonicalUnit | None = None,
    include_invalid: bool = False,
) -> HarmonizedAggregationResponse:
    response = aggregate_harmonized_observations(
        group_by=group_by,
        metric=metric,
        include_invalid=include_invalid,
        filters=HarmonizedObservationFilters(
            upload_session_id=upload_session_id,
            variable=variable,
            variety=variety,
            location=location,
            treatment=treatment,
            plot_id=plot_id,
            observation_date_from=observation_date_from,
            observation_date_to=observation_date_to,
            validation_status=validation_status,
            quality_flag=quality_flag,
            normalized_unit=normalized_unit,
        ),
    )
    return HarmonizedAggregationResponse.model_validate(response)


@app.get("/api/harmonized/query-metadata", response_model=HarmonizedQueryMetadataResponse)
def read_harmonized_query_metadata() -> HarmonizedQueryMetadataResponse:
    response = get_harmonized_query_metadata()
    return HarmonizedQueryMetadataResponse.model_validate(response)


@app.post("/api/harmonized/nl-query", response_model=NLQueryResponse)
def execute_harmonized_nl_query(payload: NLQueryRequest) -> NLQueryResponse:
    response = execute_nl_query(question=payload.question)
    return NLQueryResponse.model_validate(response)


@app.post("/api/rag/answer", response_model=AnswerResponse)
def generate_rag_answer(payload: AnswerRequest) -> AnswerResponse:
    response = build_answer_bundle(
        question=payload.question,
        upload_session_id=payload.upload_session_id,
        variable=payload.variable,
        include_context=payload.include_context,
        include_schema_context=payload.include_schema_context,
        include_raw_context=payload.include_raw_context,
    )
    return AnswerResponse.model_validate(response)


@app.get("/api/retrieval/context", response_model=RetrievalContextResponse)
def read_retrieval_context(
    upload_session_id: str | None = None,
    variable: CanonicalMeasure | None = None,
    question: str | None = Query(default=None, max_length=500),
    include_schema_context: bool = True,
    include_raw_context: bool = True,
    limit: int = Query(default=8, ge=1, le=20),
) -> RetrievalContextResponse:
    response = retrieve_query_context(
        upload_session_id=upload_session_id,
        variable=variable,
        question=question,
        include_schema_context=include_schema_context,
        include_raw_context=include_raw_context,
        limit=limit,
    )
    return RetrievalContextResponse.model_validate(response)


@app.post("/api/retrieval/search", response_model=RetrievalSearchResponse)
def search_retrieval(payload: RetrievalSearchRequest) -> RetrievalSearchResponse:
    response = search_retrieval_context(
        query=payload.query,
        upload_session_id=payload.upload_session_id,
        limit=payload.limit,
    )
    return RetrievalSearchResponse.model_validate(response)


@app.get("/api/mcp/tools", response_model=MCPToolsListResponse)
def list_mcp_tools() -> MCPToolsListResponse:
    tools = default_mcp_server().list_tools()
    return MCPToolsListResponse(count=len(tools), tools=tools)


@app.post("/api/mcp/invoke", response_model=MCPInvokeResponse)
def invoke_mcp_tool(
    payload: MCPInvokeRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> MCPInvokeResponse:
    response = default_mcp_server().invoke_by_name(
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        correlation_id=x_correlation_id,
    )
    return MCPInvokeResponse.model_validate(response)


@app.get("/api/mcp/audit", response_model=MCPAuditListResponse)
def read_mcp_audit_log(
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> MCPAuditListResponse:
    response = build_audit_list_response(correlation_id=correlation_id, limit=limit)
    return MCPAuditListResponse.model_validate(response)


@app.post("/api/text-to-sql/query", response_model=TextToSqlPipelineResponse)
def execute_text_to_sql_query(
    payload: TextToSqlPipelineRequest,
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> TextToSqlPipelineResponse:
    response = run_text_to_sql_pipeline(
        question=payload.question,
        upload_session_id=payload.upload_session_id,
        limit=payload.limit,
        explain=payload.explain,
        mode=payload.mode,
        correlation_id=x_correlation_id,
    )
    return TextToSqlPipelineResponse.model_validate(response)


@app.get("/api/text-to-sql/benchmark")
def read_text_to_sql_benchmark() -> dict[str, object]:
    report = run_text_to_sql_benchmark()
    return report.to_dict()


@app.get("/api/llm/audit", response_model=LLMAuditListResponse)
def read_llm_audit_log(
    correlation_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> LLMAuditListResponse:
    response = build_llm_audit_list_response(correlation_id=correlation_id, limit=limit)
    return LLMAuditListResponse.model_validate(response)


@app.get("/api/tools", response_model=ToolsListResponse)
def list_available_tools() -> ToolsListResponse:
    definitions = default_tool_registry().list_tools()
    return ToolsListResponse(
        count=len(definitions),
        tools=[
            ToolDefinitionResponse.model_validate(
                {
                    "tool_name": item.tool_name,
                    "description": item.description,
                    "category": item.category,
                    "read_only": item.read_only,
                    "input_fields": [
                        {
                            "name": field.name,
                            "type_name": field.type_name,
                            "required": field.required,
                            "description": field.description,
                            "default": field.default,
                        }
                        for field in item.input_fields
                    ],
                }
            )
            for item in definitions
        ],
    )


@app.post("/api/tools/execute", response_model=ToolExecuteResponse)
def execute_available_tool(payload: ToolExecuteRequest) -> ToolExecuteResponse:
    response = execute_tool(
        tool_name=payload.tool_name,
        arguments=payload.arguments,
        registry=default_tool_registry(),
    )
    return ToolExecuteResponse.model_validate(response)

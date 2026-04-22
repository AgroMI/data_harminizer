from __future__ import annotations

from typing import Any

from backend.app.mcp.server import MCPServer, default_mcp_server
from backend.app.text_to_sql.models import (
    GeneratedSql,
    QueryPlan,
    SqlExecutionResult,
    SqlValidationResult,
    TextToSqlPipelineResponse,
    ToolTraceStep,
)
from backend.app.llm.types import PlanningMetadata, PipelineMode


def run_text_to_sql_pipeline(
    *,
    question: str,
    upload_session_id: str | None = None,
    limit: int | None = None,
    explain: bool = True,
    mode: PipelineMode = "deterministic",
    correlation_id: str | None = None,
    server: MCPServer | None = None,
) -> TextToSqlPipelineResponse:
    resolved_server = server or default_mcp_server()
    trace: list[ToolTraceStep] = []

    plan_response = resolved_server.invoke_by_name(
        tool_name="plan_query",
        arguments={
            "question": question,
            "upload_session_id": upload_session_id,
            "limit": limit,
            "explain": explain,
            "mode": mode,
        },
        correlation_id=correlation_id,
    )
    resolved_correlation_id = str(plan_response["correlation_id"])
    trace.append(_trace_step(plan_response))

    if not plan_response["success"]:
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status="unsupported",
            result_type="unsupported",
            query_plan=QueryPlan(
                status="unsupported",
                intent="unsupported",
                source_relation="safe.harmonized_observations_v1",
                result_type="unsupported",
            ),
            answer={},
            explanation=[plan_response["error"]["message"]],
            tool_trace=trace,
            planning_metadata=PlanningMetadata(requested_mode=mode, applied_mode="deterministic"),
        )

    plan_payload = plan_response["result"]
    query_plan = QueryPlan.model_validate(plan_payload["query_plan"])
    explanation = list(plan_payload.get("explanation", []))
    planning_metadata = PlanningMetadata.model_validate(plan_payload.get("planning_metadata") or {})

    if not query_plan.supported:
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status=query_plan.status,
            result_type="unsupported",
            query_plan=query_plan,
            answer={},
            explanation=explanation,
            tool_trace=trace,
            planning_metadata=planning_metadata,
        )

    sql_response = resolved_server.invoke_by_name(
        tool_name="generate_sql",
        arguments={"query_plan": query_plan.model_dump(mode="json")},
        correlation_id=resolved_correlation_id,
    )
    trace.append(_trace_step(sql_response))
    if not sql_response["success"]:
        explanation.append(sql_response["error"]["message"])
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status="unsupported",
            result_type="unsupported",
            query_plan=query_plan,
            answer={},
            explanation=explanation,
            tool_trace=trace,
            planning_metadata=planning_metadata,
        )
    generated_sql = GeneratedSql.model_validate(sql_response["result"])

    validation_response = resolved_server.invoke_by_name(
        tool_name="validate_sql",
        arguments={
            "sql": generated_sql.sql,
            "parameters": generated_sql.parameters,
            "query_plan": query_plan.model_dump(mode="json"),
        },
        correlation_id=resolved_correlation_id,
    )
    trace.append(_trace_step(validation_response))
    if not validation_response["success"]:
        explanation.append(validation_response["error"]["message"])
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status="unsupported",
            result_type="unsupported",
            query_plan=query_plan,
            generated_sql=generated_sql,
            answer={},
            explanation=explanation,
            tool_trace=trace,
            planning_metadata=planning_metadata,
        )
    validation_payload = validation_response["result"]
    validation = SqlValidationResult.model_validate(validation_payload["validation"])

    if not validation.valid:
        explanation.extend(item.message for item in validation.issues)
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status="unsupported",
            result_type="unsupported",
            query_plan=query_plan,
            generated_sql=generated_sql,
            validation=validation,
            answer={},
            explanation=explanation,
            tool_trace=trace,
            planning_metadata=planning_metadata,
        )

    execution_response = resolved_server.invoke_by_name(
        tool_name="execute_sql",
        arguments={
            "sql": generated_sql.sql,
            "parameters": generated_sql.parameters,
            "query_plan": query_plan.model_dump(mode="json"),
        },
        correlation_id=resolved_correlation_id,
    )
    trace.append(_trace_step(execution_response))
    if not execution_response["success"]:
        explanation.append(execution_response["error"]["message"])
        return TextToSqlPipelineResponse(
            correlation_id=resolved_correlation_id,
            question=question,
            status="unsupported",
            result_type="unsupported",
            query_plan=query_plan,
            generated_sql=generated_sql,
            validation=validation,
            answer={},
            explanation=explanation,
            tool_trace=trace,
        )
    execution_payload = execution_response["result"]
    execution = SqlExecutionResult.model_validate(execution_payload["execution"])
    answer = _package_answer(query_plan=query_plan, execution=execution)

    return TextToSqlPipelineResponse(
        correlation_id=resolved_correlation_id,
        question=question,
        status=query_plan.status,
        result_type=query_plan.result_type,
        query_plan=query_plan,
        generated_sql=generated_sql,
        validation=validation,
        execution=execution,
        answer=answer,
        explanation=explanation,
        tool_trace=trace,
        planning_metadata=planning_metadata,
    )


def _package_answer(*, query_plan: QueryPlan, execution: SqlExecutionResult) -> dict[str, Any]:
    if query_plan.result_type == "records":
        return {
            "records": execution.rows,
            "count": execution.row_count,
        }
    if query_plan.result_type == "aggregation":
        return {
            "items": execution.rows,
            "count": execution.row_count,
        }
    return {}


def _trace_step(response: dict[str, Any]) -> ToolTraceStep:
    metadata = response.get("metadata") or {}
    error = response.get("error") or {}
    return ToolTraceStep(
        tool_name=str(response["tool_name"]),
        success=bool(response["success"]),
        error_code=error.get("code"),
        duration_ms=metadata.get("duration_ms"),
    )

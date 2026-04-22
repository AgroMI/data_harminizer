"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { WorkflowStepper } from "../components/WorkflowStepper";
import type {
  BenchmarkReport,
  MCPAuditEntry,
  MCPAuditResponse,
  MCPInvokeResponse,
  MCPToolDefinition,
  MCPToolsResponse,
  PipelineMode,
  TextToSqlExecution,
  TextToSqlPipelineResponse
} from "../lib/api_types";
import { API_BASE, readProblemDetail, toErrorMessage } from "../lib/client";
import { primaryWorkflowSteps } from "../lib/workflow";

type AITabKey = "ask" | "tools" | "audit" | "benchmark";

const TABS: Array<{ key: AITabKey; label: string }> = [
  { key: "ask", label: "Ask" },
  { key: "tools", label: "MCP tools" },
  { key: "audit", label: "Audit" },
  { key: "benchmark", label: "Benchmark" }
];

const EXAMPLE_QUESTIONS = [
  "Average yield by variety",
  "Count observations by validation status",
  "Show warning records",
  "Average moisture by treatment"
];
const DEFAULT_QUERY_MODE: PipelineMode = "local_llm_hybrid";

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2);
}

function ResultTable({ execution }: { execution: TextToSqlExecution | null }) {
  if (!execution || execution.rows.length === 0) {
    return <EmptyState title="No rows returned" body="Run a supported question to see result rows here." />;
  }

  return (
    <div className="overflow-x-auto rounded-[1.25rem] border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            {execution.columns.map((column) => (
              <th key={column} className="px-4 py-3 font-semibold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {execution.rows.map((row, index) => (
            <tr key={`${index}-${JSON.stringify(row)}`}>
              {execution.columns.map((column) => (
                <td key={`${index}-${column}`} className="px-4 py-3 text-slate-700">
                  {String(row[column] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AIPage() {
  return (
    <Suspense
      fallback={
        <section className="surface-card flex min-h-[320px] items-center justify-center px-6 py-10">
          <p className="text-sm font-medium text-slate-500">Loading AI workspace...</p>
        </section>
      }
    >
      <AIPageContent />
    </Suspense>
  );
}

function AIPageContent() {
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<AITabKey>("ask");
  const [uploadSessionId, setUploadSessionId] = useState("");
  const [question, setQuestion] = useState(EXAMPLE_QUESTIONS[0]);
  const [questionResult, setQuestionResult] = useState<TextToSqlPipelineResponse | null>(null);
  const [questionState, setQuestionState] = useState("");
  const [questionError, setQuestionError] = useState("");

  const [tools, setTools] = useState<MCPToolDefinition[]>([]);
  const [selectedToolName, setSelectedToolName] = useState("describe_schema");
  const [toolInput, setToolInput] = useState('{\n  "include_live_metadata": true\n}');
  const [toolResult, setToolResult] = useState<MCPInvokeResponse | null>(null);
  const [toolState, setToolState] = useState("");
  const [toolError, setToolError] = useState("");

  const [correlationIdFilter, setCorrelationIdFilter] = useState("");
  const [auditEntries, setAuditEntries] = useState<MCPAuditEntry[]>([]);
  const [auditState, setAuditState] = useState("");
  const [auditError, setAuditError] = useState("");
  const [selectedAuditEntry, setSelectedAuditEntry] = useState<MCPAuditEntry | null>(null);

  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [benchmarkState, setBenchmarkState] = useState("");
  const [benchmarkError, setBenchmarkError] = useState("");

  useEffect(() => {
    const nextUploadSessionId = searchParams.get("upload_session_id") || "";
    setUploadSessionId(nextUploadSessionId);
  }, [searchParams]);

  useEffect(() => {
    void loadTools();
  }, []);

  useEffect(() => {
    if (questionResult?.correlation_id) {
      setCorrelationIdFilter(questionResult.correlation_id);
    }
  }, [questionResult]);

  const selectedTool = useMemo(
    () => tools.find((tool) => tool.tool_name === selectedToolName) || null,
    [selectedToolName, tools]
  );

  async function loadTools(): Promise<void> {
    try {
      const response = await fetch(`${API_BASE}/api/mcp/tools`);
      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to load MCP tool list."));
      }
      const payload = (await response.json()) as MCPToolsResponse;
      setTools(payload.tools || []);
      if (payload.tools[0]) {
        const firstTool = payload.tools[0].tool_name;
        setSelectedToolName(firstTool);
        setToolInput(defaultToolInput(firstTool));
      }
    } catch {
      setTools([]);
    }
  }

  async function runQuestion(): Promise<void> {
    if (!question.trim()) {
      setQuestionError("Enter a question first.");
      return;
    }

    setQuestionState("Running question...");
    setQuestionError("");

    try {
      const response = await fetch(`${API_BASE}/api/text-to-sql/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          upload_session_id: uploadSessionId.trim() || null,
          explain: true,
          mode: DEFAULT_QUERY_MODE
        })
      });

      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to run AI query."));
      }

      const payload = (await response.json()) as TextToSqlPipelineResponse;
      setQuestionResult(payload);
      setQuestionState(payload.status === "supported" ? "Query completed." : "Query returned a controlled rejection.");
    } catch (caught) {
      setQuestionResult(null);
      setQuestionError(toErrorMessage(caught, "Failed to run AI query."));
      setQuestionState("");
    }
  }

  async function runTool(): Promise<void> {
    setToolState("Running tool...");
    setToolError("");
    try {
      const parsed = JSON.parse(toolInput) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Tool input must be a JSON object.");
      }

      const response = await fetch(`${API_BASE}/api/mcp/invoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_name: selectedToolName,
          arguments: parsed
        })
      });

      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to run MCP tool."));
      }

      const payload = (await response.json()) as MCPInvokeResponse;
      setToolResult(payload);
      setToolState(payload.success ? "Tool completed." : "Tool returned an error response.");
    } catch (caught) {
      setToolResult(null);
      setToolError(toErrorMessage(caught, "Failed to run MCP tool."));
      setToolState("");
    }
  }

  async function loadAudit(): Promise<void> {
    setAuditState("Loading audit...");
    setAuditError("");
    try {
      const params = new URLSearchParams();
      params.set("limit", "50");
      if (correlationIdFilter.trim()) {
        params.set("correlation_id", correlationIdFilter.trim());
      }

      const response = await fetch(`${API_BASE}/api/mcp/audit?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to load audit entries."));
      }

      const payload = (await response.json()) as MCPAuditResponse;
      setAuditEntries(payload.items || []);
      setSelectedAuditEntry(payload.items[0] || null);
      setAuditState(`Loaded ${payload.count} entries.`);
    } catch (caught) {
      setAuditEntries([]);
      setSelectedAuditEntry(null);
      setAuditError(toErrorMessage(caught, "Failed to load audit entries."));
      setAuditState("");
    }
  }

  async function loadBenchmark(): Promise<void> {
    setBenchmarkState("Loading benchmark...");
    setBenchmarkError("");
    try {
      const response = await fetch(`${API_BASE}/api/text-to-sql/benchmark`);
      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to load benchmark."));
      }
      const payload = (await response.json()) as BenchmarkReport;
      setBenchmark(payload);
      setBenchmarkState(`Loaded ${payload.total_questions} benchmark questions.`);
    } catch (caught) {
      setBenchmark(null);
      setBenchmarkError(toErrorMessage(caught, "Failed to load benchmark."));
      setBenchmarkState("");
    }
  }

  return (
    <div className="grid gap-6">
      <section className="surface-card px-6 py-8 sm:px-8">
        <div className="grid gap-6 lg:grid-cols-[1.15fr,0.85fr]">
          <div className="space-y-5">
            <div className="space-y-3">
              <p className="eyebrow">Step 7</p>
              <h1 className="text-4xl font-semibold tracking-tight text-slate-950">AI query and advanced tools</h1>
              <p className="max-w-3xl text-base leading-7 text-slate-600">
                The primary surface is the question box. Technical detail still exists, but it stays behind tabs and collapsible sections instead of dominating the page.
              </p>
            </div>

            <WorkflowStepper steps={primaryWorkflowSteps()} activeKey="ai" />

            <div className="flex flex-wrap gap-3">
              <Link href={uploadSessionId ? `/workspace?upload_session_id=${encodeURIComponent(uploadSessionId)}` : "/workspace"} className="btn-ghost px-6">
                Back to workspace
              </Link>
              <Link href="/upload" className="btn-ghost px-6">
                Upload new workbook
              </Link>
            </div>
          </div>

          <div className="surface-card-muted p-5">
            <p className="eyebrow">Scope</p>
            <label className="mt-3 grid gap-2">
              <span className="text-sm font-medium text-slate-700">Upload session</span>
              <input
                className="input-shell"
                value={uploadSessionId}
                onChange={(event) => setUploadSessionId(event.target.value)}
                placeholder="Optional scope"
              />
            </label>
            <label className="mt-4 grid gap-2">
              <span className="text-sm font-medium text-slate-700">Execution mode</span>
              <div className="input-shell flex min-h-11 items-center text-slate-700">
                Local AI Hybrid
              </div>
            </label>
          </div>
        </div>
      </section>

      <section className="surface-card p-3">
        <div className="flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                activeTab === tab.key
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "ask" ? (
        <div className="grid gap-6">
          <section className="surface-card p-6">
            <div className="grid gap-6 lg:grid-cols-[1.1fr,0.9fr]">
              <div className="space-y-4">
                <div>
                  <p className="eyebrow">Ask a question</p>
                  <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Natural language query</h2>
                </div>

                <textarea
                  className="input-shell min-h-[150px]"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Average yield by variety"
                />

                <div className="flex flex-wrap gap-2">
                  {EXAMPLE_QUESTIONS.map((item) => (
                    <button key={item} type="button" className="btn-ghost min-h-10 px-4" onClick={() => setQuestion(item)}>
                      {item}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-3">
                  <button type="button" className="btn-primary px-6" onClick={() => void runQuestion()}>
                    Run AI query
                  </button>
                  {questionResult?.correlation_id ? (
                    <button
                      type="button"
                      className="btn-ghost px-6"
                      onClick={() => {
                        setActiveTab("audit");
                        void loadAudit();
                      }}
                    >
                      Open audit
                    </button>
                  ) : null}
                </div>

                {questionState ? <p className="text-sm text-slate-600">{questionState}</p> : null}
                {questionError ? <Notice tone="error">{questionError}</Notice> : null}
              </div>

              <div className="surface-card-muted p-5">
                <p className="eyebrow">Answer</p>
                <h2 className="text-xl font-semibold tracking-tight text-slate-950">Result</h2>
                <div className="mt-4">
                  <ResultTable execution={questionResult?.execution || null} />
                </div>
              </div>
            </div>
          </section>

          {questionResult?.explanation?.length ? (
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Explanation</p>
              <div className="mt-4 grid gap-2">
                {questionResult.explanation.map((item) => (
                  <p key={item} className="text-sm leading-6 text-slate-600">
                    {item}
                  </p>
                ))}
              </div>
            </section>
          ) : null}

          {questionResult?.planning_metadata ? (
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Planning metadata</p>
              <div className="mt-4 grid gap-2 text-sm text-slate-600">
                <p>Requested mode: <strong>{questionResult.planning_metadata.requested_mode}</strong></p>
                <p>Applied mode: <strong>{questionResult.planning_metadata.applied_mode}</strong></p>
                <p>Plan origin: <strong>{questionResult.planning_metadata.plan_origin}</strong></p>
                <p>LLM attempted: <strong>{questionResult.planning_metadata.llm_attempted ? "yes" : "no"}</strong></p>
                <p>Fallback used: <strong>{questionResult.planning_metadata.fallback_used ? "yes" : "no"}</strong></p>
                <p>Fallback reason: <strong>{questionResult.planning_metadata.fallback_reason || "n/a"}</strong></p>
                <p>LLM used: <strong>{questionResult.planning_metadata.llm_used ? "yes" : "no"}</strong></p>
                <p>Tool orchestration: <strong>{questionResult.planning_metadata.orchestration_used ? "yes" : "no"}</strong></p>
                <p>Orchestration steps: <strong>{questionResult.planning_metadata.orchestration_steps.join(", ") || "n/a"}</strong></p>
              </div>
            </section>
          ) : null}

          <section className="grid gap-4">
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-lg font-semibold text-slate-900">Query plan</summary>
              <pre className="code-panel mt-4">{prettyJson(questionResult?.query_plan)}</pre>
            </details>
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-lg font-semibold text-slate-900">Generated SQL</summary>
              <pre className="code-panel mt-4">{prettyJson(questionResult?.generated_sql)}</pre>
            </details>
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-lg font-semibold text-slate-900">Validation</summary>
              <pre className="code-panel mt-4">{prettyJson(questionResult?.validation)}</pre>
            </details>
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-lg font-semibold text-slate-900">Tool trace</summary>
              <pre className="code-panel mt-4">{prettyJson(questionResult?.tool_trace)}</pre>
            </details>
          </section>
        </div>
      ) : null}

      {activeTab === "tools" ? (
        <section className="grid gap-6 lg:grid-cols-[0.95fr,1.05fr]">
          <section className="surface-card p-5">
            <div className="space-y-4">
              <div>
                <p className="eyebrow">MCP tools</p>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Direct tool invocation</h2>
              </div>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Tool</span>
                <select
                  className="input-shell"
                  value={selectedToolName}
                  onChange={(event) => {
                    setSelectedToolName(event.target.value);
                    setToolInput(defaultToolInput(event.target.value));
                  }}
                >
                  {tools.map((tool) => (
                    <option key={tool.tool_name} value={tool.tool_name}>
                      {tool.tool_name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Input JSON</span>
                <textarea
                  className="input-shell min-h-[260px] font-mono text-xs leading-6"
                  value={toolInput}
                  onChange={(event) => setToolInput(event.target.value)}
                  spellCheck={false}
                />
              </label>

              <div className="flex flex-wrap gap-3">
                <button type="button" className="btn-primary px-6" onClick={() => void runTool()}>
                  Run tool
                </button>
              </div>

              {toolState ? <p className="text-sm text-slate-600">{toolState}</p> : null}
              {toolError ? <Notice tone="error">{toolError}</Notice> : null}
            </div>
          </section>

          <section className="grid gap-6">
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Tool contract</p>
              <pre className="code-panel mt-4">{prettyJson(selectedTool?.input_schema || {})}</pre>
            </section>
            <section className="surface-card p-5">
              <p className="eyebrow">Tool output</p>
              <pre className="code-panel mt-4">{prettyJson(toolResult)}</pre>
            </section>
          </section>
        </section>
      ) : null}

      {activeTab === "audit" ? (
        <section className="grid gap-6 lg:grid-cols-[0.95fr,1.05fr]">
          <section className="surface-card p-5">
            <div className="space-y-4">
              <div>
                <p className="eyebrow">Audit</p>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Tool invocation history</h2>
              </div>

              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Correlation ID</span>
                <input
                  className="input-shell"
                  value={correlationIdFilter}
                  onChange={(event) => setCorrelationIdFilter(event.target.value)}
                  placeholder="Optional filter"
                />
              </label>

              <button type="button" className="btn-primary px-6" onClick={() => void loadAudit()}>
                Load audit
              </button>

              {auditState ? <p className="text-sm text-slate-600">{auditState}</p> : null}
              {auditError ? <Notice tone="error">{auditError}</Notice> : null}

              <div className="grid gap-3">
                {auditEntries.map((entry, index) => (
                  <button
                    key={`${entry.correlation_id}-${entry.tool_name}-${index}`}
                    type="button"
                    className="rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:border-cyan-200"
                    onClick={() => setSelectedAuditEntry(entry)}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-semibold text-slate-900">{entry.tool_name}</p>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${entry.success ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {entry.success ? "success" : "error"}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{entry.correlation_id}</p>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="grid gap-6">
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Request</p>
              <pre className="code-panel mt-4">{prettyJson(selectedAuditEntry?.request_payload || null)}</pre>
            </section>
            <section className="surface-card p-5">
              <p className="eyebrow">Response</p>
              <pre className="code-panel mt-4">{prettyJson(selectedAuditEntry?.response_payload || null)}</pre>
            </section>
          </section>
        </section>
      ) : null}

      {activeTab === "benchmark" ? (
        <section className="grid gap-6">
          <section className="surface-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="eyebrow">Benchmark</p>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Evaluation summary</h2>
              </div>
              <button type="button" className="btn-primary px-6" onClick={() => void loadBenchmark()}>
                Load benchmark
              </button>
            </div>

            {benchmarkState ? <p className="mt-4 text-sm text-slate-600">{benchmarkState}</p> : null}
            {benchmarkError ? <Notice tone="error">{benchmarkError}</Notice> : null}

            {benchmark ? (
              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <MetricCard title="Query plan correctness" correct={benchmark.query_plan_correctness.correct} total={benchmark.query_plan_correctness.total} />
                <MetricCard title="SQL validity" correct={benchmark.sql_validity_rate.correct} total={benchmark.sql_validity_rate.total} />
                <MetricCard title="Execution success" correct={benchmark.execution_success_rate.correct} total={benchmark.execution_success_rate.total} />
                <MetricCard title="Answer correctness" correct={benchmark.answer_correctness.correct} total={benchmark.answer_correctness.total} />
                <MetricCard title="Unsupported queries" correct={benchmark.unsupported_query_rate.correct} total={benchmark.unsupported_query_rate.total} />
                <MetricCard title="Unsafe rejections" correct={benchmark.rejected_unsafe_query_rate.correct} total={benchmark.rejected_unsafe_query_rate.total} />
              </div>
            ) : (
              <div className="mt-5">
                <EmptyState title="No benchmark loaded" body="Load the benchmark to inspect the current evaluation summary." />
              </div>
            )}
          </section>

          {benchmark ? (
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-lg font-semibold text-slate-900">Question-level results</summary>
              <pre className="code-panel mt-4">{prettyJson(benchmark.questions)}</pre>
            </details>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function defaultToolInput(toolName: string): string {
  const defaults: Record<string, Record<string, unknown>> = {
    describe_schema: { include_live_metadata: true },
    plan_query: { question: "Average yield by variety", explain: true },
    generate_sql: {
      query_plan: {
        status: "supported",
        intent: "aggregate",
        source_relation: "safe.harmonized_observations_v1",
        selected_measures: ["yield"],
        selected_dimensions: ["variety"],
        filters: [
          { field_name: "variable", operator: "eq", value: "yield", source_text: "yield" },
          { field_name: "normalized_unit", operator: "eq", value: "kg/ha", source_text: "kg/ha" }
        ],
        aggregations: [{ function: "avg", field_name: "normalized_value", alias: "metric_value" }],
        grouping: ["variety"],
        ordering: [{ field_name: "variety", direction: "asc", source_text: "by variety" }],
        limit: 25,
        unit_handling: { mode: "canonical_normalized", normalized_unit: "kg/ha", note: "Yield normalized to kg/ha." },
        ambiguity_flags: [],
        validation_notes: [],
        trace: [],
        target_measure: "yield",
        result_type: "aggregation"
      }
    },
    validate_sql: {
      sql: "SELECT variety AS group_value, avg(normalized_value)::double precision AS metric_value, count(*)::integer AS record_count, max(normalized_unit) AS normalized_unit FROM safe.harmonized_observations_v1 WHERE variable = %s AND normalized_unit = %s AND normalized_value IS NOT NULL AND validation_status <> 'invalid' GROUP BY variety ORDER BY variety ASC NULLS LAST LIMIT %s",
      parameters: ["yield", "kg/ha", 25]
    },
    execute_sql: {
      sql: "SELECT variety AS group_value, avg(normalized_value)::double precision AS metric_value, count(*)::integer AS record_count, max(normalized_unit) AS normalized_unit FROM safe.harmonized_observations_v1 WHERE variable = %s AND normalized_unit = %s AND normalized_value IS NOT NULL AND validation_status <> 'invalid' GROUP BY variety ORDER BY variety ASC NULLS LAST LIMIT %s",
      parameters: ["yield", "kg/ha", 25],
      query_plan: {
        status: "supported",
        intent: "aggregate",
        source_relation: "safe.harmonized_observations_v1",
        selected_measures: ["yield"],
        selected_dimensions: ["variety"],
        filters: [
          { field_name: "variable", operator: "eq", value: "yield", source_text: "yield" },
          { field_name: "normalized_unit", operator: "eq", value: "kg/ha", source_text: "kg/ha" }
        ],
        aggregations: [{ function: "avg", field_name: "normalized_value", alias: "metric_value" }],
        grouping: ["variety"],
        ordering: [{ field_name: "variety", direction: "asc", source_text: "by variety" }],
        limit: 25,
        unit_handling: { mode: "canonical_normalized", normalized_unit: "kg/ha", note: "Yield normalized to kg/ha." },
        ambiguity_flags: [],
        validation_notes: [],
        trace: [],
        target_measure: "yield",
        result_type: "aggregation"
      }
    },
    explain_metadata: { query: "yield units and quality flags", limit: 5 },
    retrieve_evidence: { query: "validation flags and yield units", limit: 5 }
  };

  return prettyJson(defaults[toolName] || {});
}

function MetricCard({ title, correct, total }: { title: string; correct: number; total: number }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">
        {correct}/{total}
      </p>
    </div>
  );
}

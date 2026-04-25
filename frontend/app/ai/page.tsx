"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import type {
  BenchmarkReport,
  MCPAuditEntry,
  MCPAuditResponse,
  MCPInvokeResponse,
  MCPToolDefinition,
  MCPToolsResponse,
  TextToSqlExecution,
  TextToSqlPipelineResponse
} from "../lib/api_types";
import { API_BASE, cn, formatNumber, readProblemDetail, toErrorMessage } from "../lib/client";

type AITabKey = "ask" | "tools" | "audit" | "benchmark";
type QueryOutcome = "idle" | "running" | "success" | "empty" | "schema_info" | "unsupported";

const TABS: Array<{ key: AITabKey; label: string }> = [
  { key: "ask", label: "Ask" },
  { key: "tools", label: "MCP tools" },
  { key: "audit", label: "Audit" },
  { key: "benchmark", label: "Benchmark" }
];

const EXAMPLE_QUESTIONS = [
  "Average yield by variety",
  "Show warning records",
  "Count by validation status",
  "Average moisture by treatment",
];

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2);
}

function determineOutcome(
  result: TextToSqlPipelineResponse | null,
  running: boolean
): QueryOutcome {
  if (running) return "running";
  if (!result) return "idle";
  if (result.status === "supported") {
    return (result.execution?.row_count ?? 0) > 0 ? "success" : "empty";
  }
  if (
    result.planning_metadata?.fallback_reason === "reject" &&
    result.explanation.some((e) => e.length > 20)
  ) {
    return "schema_info";
  }
  return "unsupported";
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return formatNumber(value, "—");
  return String(value);
}

function DataTable({ execution }: { execution: TextToSqlExecution }) {
  return (
    <div className="overflow-x-auto rounded-[1.25rem] border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left">
          <tr>
            {execution.columns.map((col) => (
              <th key={col} className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                {col.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {execution.rows.map((row, i) => (
            <tr key={i} className="transition-colors hover:bg-slate-50/60">
              {execution.columns.map((col) => (
                <td key={col} className="px-4 py-3 text-slate-700">
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultPanel({
  outcome,
  result,
  error
}: {
  outcome: QueryOutcome;
  result: TextToSqlPipelineResponse | null;
  error: string;
}) {
  if (error) {
    return <Notice tone="error" title="Query failed">{error}</Notice>;
  }

  if (outcome === "idle") {
    return (
      <section className="surface-card flex min-h-[200px] flex-col items-center justify-center gap-3 p-8 text-center">
        <svg className="h-10 w-10 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
        </svg>
        <div>
          <p className="font-semibold text-slate-400">Ready to query</p>
          <p className="mt-1 text-sm text-slate-400">Pick an example or type a question, then press Run.</p>
        </div>
      </section>
    );
  }

  if (outcome === "running") {
    return (
      <section className="surface-card flex min-h-[200px] items-center justify-center p-8">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-cyan-600" />
          <p className="text-sm font-medium text-slate-500">Running query…</p>
        </div>
      </section>
    );
  }

  if (outcome === "success") {
    const execution = result!.execution!;
    return (
      <section className="surface-card overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100">
              <svg className="h-4 w-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
            </span>
            <h2 className="text-lg font-semibold text-slate-950">Result</h2>
          </div>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
            {execution.row_count} {execution.row_count === 1 ? "row" : "rows"}
            {execution.truncated ? " · truncated" : ""}
          </span>
        </div>
        <div className="p-5">
          <DataTable execution={execution} />
        </div>
        {result!.explanation?.length ? (
          <div className="border-t border-slate-100 px-5 pb-4 pt-3">
            {result!.explanation.map((item, i) => (
              <p key={i} className="text-sm leading-6 text-slate-500">{item}</p>
            ))}
          </div>
        ) : null}
      </section>
    );
  }

  if (outcome === "empty") {
    return (
      <section className="surface-card p-6">
        <div className="flex items-start gap-4">
          <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-slate-100">
            <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 15.803 7.5 7.5 0 0 0 15.803 15.803Z" />
            </svg>
          </span>
          <div>
            <h2 className="text-base font-semibold text-slate-900">No matching data</h2>
            <p className="mt-1 text-sm text-slate-500">The query executed successfully but returned zero rows for these filters.</p>
            {result!.explanation?.length ? (
              <div className="mt-3 grid gap-1">
                {result!.explanation.map((item, i) => (
                  <p key={i} className="text-sm leading-6 text-slate-600">{item}</p>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  if (outcome === "schema_info") {
    return (
      <section className="rounded-[1.25rem] border border-cyan-200 bg-gradient-to-br from-cyan-50 to-white p-6">
        <div className="flex items-start gap-4">
          <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-cyan-100">
            <svg className="h-5 w-5 text-cyan-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-cyan-600">Schema answer</p>
            <div className="mt-3 grid gap-2">
              {result!.explanation.map((item, i) => (
                <p key={i} className="text-sm leading-7 text-slate-700">{item}</p>
              ))}
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-[1.25rem] border border-amber-200 bg-amber-50 p-6">
      <div className="flex items-start gap-4">
        <span className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-amber-100">
          <svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </span>
        <div>
          <h2 className="text-base font-semibold text-slate-900">Query not supported</h2>
          {result!.explanation?.length ? (
            <div className="mt-2 grid gap-1">
              {result!.explanation.map((item, i) => (
                <p key={i} className="text-sm leading-6 text-slate-700">{item}</p>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-slate-700">
              This question could not be mapped to a supported data query. Try phrasing like "yield by variety", "show records with warnings", or "count by status".
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function PlanningStrip({ result }: { result: TextToSqlPipelineResponse }) {
  const meta = result.planning_metadata;
  const modeLabel: Record<string, string> = {
    local_llm_hybrid: "Local AI Hybrid",
    local_llm_tool_orchestrated: "Tool Orchestrated",
    deterministic: "Deterministic"
  };
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-[1.25rem] border border-slate-200 bg-white px-5 py-3 text-sm">
      <Chip label="Mode" value={modeLabel[meta.applied_mode] || meta.applied_mode} />
      <Chip
        label="Origin"
        value={meta.plan_origin === "local_llm" ? "Local LLM" : "Deterministic"}
        tone={meta.plan_origin === "local_llm" ? "cyan" : "neutral"}
      />
      <Chip
        label="LLM"
        value={meta.llm_used ? "used" : "not used"}
        tone={meta.llm_used ? "green" : "neutral"}
      />
      {meta.fallback_used ? (
        <Chip label="Fallback" value={meta.fallback_reason || "yes"} tone="amber" />
      ) : null}
      {result.tool_trace.length > 0 ? (
        <div className="flex items-center gap-2">
          <span className="text-slate-400">Pipeline</span>
          <span className="font-medium text-slate-600">
            {result.tool_trace.map((step, i) => (
              <span key={i}>
                {i > 0 ? <span className="mx-1 text-slate-300">→</span> : null}
                <span className={step.success ? "" : "text-rose-600"}>
                  {step.tool_name.replace(/_/g, " ")}
                </span>
              </span>
            ))}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function Chip({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "neutral" | "green" | "cyan" | "amber";
}) {
  const valueClass = {
    neutral: "text-slate-700",
    green: "text-emerald-700",
    cyan: "text-cyan-700",
    amber: "text-amber-700"
  }[tone];
  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-400">{label}</span>
      <span className={cn("font-semibold", valueClass)}>{value}</span>
    </div>
  );
}

function TechDetails({ result }: { result: TextToSqlPipelineResponse }) {
  const sections: Array<{ label: string; data: unknown; show: boolean }> = [
    { label: "Query plan", data: result.query_plan, show: true },
    { label: "Generated SQL", data: result.generated_sql, show: result.generated_sql !== null },
    { label: "Validation", data: result.validation, show: result.validation !== null },
    { label: "Tool trace", data: result.tool_trace, show: true }
  ];
  return (
    <div className="grid gap-3">
      {sections.filter((s) => s.show).map((section) => (
        <details key={section.label} className="surface-card px-5 py-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700 marker:text-slate-400">
            {section.label}
          </summary>
          <pre className="code-panel mt-4">{prettyJson(section.data)}</pre>
        </details>
      ))}
    </div>
  );
}

export default function AIPage() {
  return (
    <Suspense
      fallback={
        <section className="surface-card flex min-h-[320px] items-center justify-center px-6 py-10">
          <p className="text-sm font-medium text-slate-500">Loading AI workspace…</p>
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
  const [isRunning, setIsRunning] = useState(false);
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

  const outcome = useMemo(
    () => determineOutcome(questionResult, isRunning),
    [questionResult, isRunning]
  );

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
      if (!response.ok) throw new Error(await readProblemDetail(response, "Failed to load tools."));
      const payload = (await response.json()) as MCPToolsResponse;
      setTools(payload.tools || []);
      if (payload.tools[0]) {
        setSelectedToolName(payload.tools[0].tool_name);
        setToolInput(defaultToolInput(payload.tools[0].tool_name));
      }
    } catch {
      setTools([]);
    }
  }

  async function runQuestion(): Promise<void> {
    if (!question.trim()) return;
    setIsRunning(true);
    setQuestionError("");
    setQuestionResult(null);
    try {
      const response = await fetch(`${API_BASE}/api/text-to-sql/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          upload_session_id: uploadSessionId.trim() || null,
          explain: true,
          mode: "local_llm_hybrid"
        })
      });
      if (!response.ok) throw new Error(await readProblemDetail(response, "Failed to run query."));
      const payload = (await response.json()) as TextToSqlPipelineResponse;
      setQuestionResult(payload);
    } catch (caught) {
      setQuestionError(toErrorMessage(caught, "Failed to run query."));
    } finally {
      setIsRunning(false);
    }
  }

  async function runTool(): Promise<void> {
    setToolState("Running…");
    setToolError("");
    try {
      const parsed = JSON.parse(toolInput) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Tool input must be a JSON object.");
      }
      const response = await fetch(`${API_BASE}/api/mcp/invoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_name: selectedToolName, arguments: parsed })
      });
      if (!response.ok) throw new Error(await readProblemDetail(response, "Failed to run tool."));
      const payload = (await response.json()) as MCPInvokeResponse;
      setToolResult(payload);
      setToolState(payload.success ? "Completed." : "Tool returned an error.");
    } catch (caught) {
      setToolResult(null);
      setToolError(toErrorMessage(caught, "Failed to run tool."));
      setToolState("");
    }
  }

  async function loadAudit(): Promise<void> {
    setAuditState("Loading…");
    setAuditError("");
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (correlationIdFilter.trim()) params.set("correlation_id", correlationIdFilter.trim());
      const response = await fetch(`${API_BASE}/api/mcp/audit?${params.toString()}`);
      if (!response.ok) throw new Error(await readProblemDetail(response, "Failed to load audit."));
      const payload = (await response.json()) as MCPAuditResponse;
      setAuditEntries(payload.items || []);
      setSelectedAuditEntry(payload.items[0] || null);
      setAuditState(`${payload.count} entries.`);
    } catch (caught) {
      setAuditEntries([]);
      setAuditError(toErrorMessage(caught, "Failed to load audit."));
      setAuditState("");
    }
  }

  async function loadBenchmark(): Promise<void> {
    setBenchmarkState("Loading…");
    setBenchmarkError("");
    try {
      const response = await fetch(`${API_BASE}/api/text-to-sql/benchmark`);
      if (!response.ok) throw new Error(await readProblemDetail(response, "Failed to load benchmark."));
      const payload = (await response.json()) as BenchmarkReport;
      setBenchmark(payload);
      setBenchmarkState(`${payload.total_questions} questions.`);
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
              <h1 className="text-4xl font-semibold tracking-tight text-slate-950">AI query workspace</h1>
              <p className="max-w-3xl text-base leading-7 text-slate-600">
                Ask questions in plain language. The AI plans a safe query, generates and validates SQL, then returns a clean result.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href={uploadSessionId ? `/workspace?upload_session_id=${encodeURIComponent(uploadSessionId)}` : "/workspace"}
                className="btn-ghost px-6"
              >
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
                onChange={(e) => setUploadSessionId(e.target.value)}
                placeholder="Leave empty to query all uploads"
              />
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
              className={cn(
                "rounded-full px-4 py-2 text-sm font-semibold transition",
                activeTab === tab.key
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              )}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {activeTab === "ask" ? (
        <div className="grid gap-5">
          <section className="surface-card p-6">
            <div className="space-y-4">
              <div>
                <p className="eyebrow">Ask a question</p>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Natural language query</h2>
              </div>
              <textarea
                className="input-shell min-h-[100px] resize-none"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void runQuestion();
                  }
                }}
                placeholder="Average yield by variety"
                disabled={isRunning}
              />
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="btn-ghost min-h-9 px-3 text-xs"
                    onClick={() => setQuestion(q)}
                    disabled={isRunning}
                  >
                    {q}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  className="btn-primary px-6"
                  onClick={() => void runQuestion()}
                  disabled={isRunning || !question.trim()}
                >
                  {isRunning ? "Running…" : "Run AI query"}
                </button>
                {questionResult?.correlation_id ? (
                  <button
                    type="button"
                    className="btn-ghost px-5"
                    onClick={() => { setActiveTab("audit"); void loadAudit(); }}
                  >
                    Open audit
                  </button>
                ) : null}
              </div>
            </div>
          </section>

          <ResultPanel outcome={outcome} result={questionResult} error={questionError} />

          {questionResult && !isRunning ? (
            <PlanningStrip result={questionResult} />
          ) : null}

          {questionResult && !isRunning ? (
            <TechDetails result={questionResult} />
          ) : null}
        </div>
      ) : null}

      {activeTab === "tools" ? (
        <section className="grid gap-6 lg:grid-cols-[0.95fr,1.05fr]">
          <section className="surface-card p-5">
            <div className="space-y-4">
              <div>
                <p className="eyebrow">MCP tools</p>
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Direct invocation</h2>
              </div>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Tool</span>
                <select
                  className="input-shell"
                  value={selectedToolName}
                  onChange={(e) => {
                    setSelectedToolName(e.target.value);
                    setToolInput(defaultToolInput(e.target.value));
                  }}
                >
                  {tools.map((tool) => (
                    <option key={tool.tool_name} value={tool.tool_name}>
                      {tool.tool_name}
                    </option>
                  ))}
                </select>
              </label>
              {selectedTool ? (
                <p className="text-sm leading-6 text-slate-600">{selectedTool.description}</p>
              ) : null}
              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Input JSON</span>
                <textarea
                  className="input-shell min-h-[260px] font-mono text-xs leading-6"
                  value={toolInput}
                  onChange={(e) => setToolInput(e.target.value)}
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

          <section className="grid gap-4 self-start">
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Input schema</p>
              <pre className="code-panel mt-4">{prettyJson(selectedTool?.input_schema || {})}</pre>
            </section>
            <section className="surface-card p-5">
              <p className="eyebrow">Output</p>
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
                <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Invocation history</h2>
              </div>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-slate-700">Correlation ID</span>
                <input
                  className="input-shell"
                  value={correlationIdFilter}
                  onChange={(e) => setCorrelationIdFilter(e.target.value)}
                  placeholder="Optional filter"
                />
              </label>
              <button type="button" className="btn-primary px-6" onClick={() => void loadAudit()}>
                Load audit
              </button>
              {auditState ? <p className="text-sm text-slate-600">{auditState}</p> : null}
              {auditError ? <Notice tone="error">{auditError}</Notice> : null}
              <div className="grid gap-3">
                {auditEntries.map((entry, i) => (
                  <button
                    key={`${entry.correlation_id}-${entry.tool_name}-${i}`}
                    type="button"
                    className={cn(
                      "rounded-[1.25rem] border px-4 py-4 text-left transition",
                      selectedAuditEntry?.correlation_id === entry.correlation_id
                        ? "border-cyan-200 bg-cyan-50"
                        : "border-slate-200 bg-slate-50 hover:border-cyan-200"
                    )}
                    onClick={() => setSelectedAuditEntry(entry)}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-semibold text-slate-900">{entry.tool_name}</p>
                      <span className={cn(
                        "rounded-full px-3 py-0.5 text-xs font-semibold",
                        entry.success ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                      )}>
                        {entry.success ? "success" : "error"}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-500">{entry.correlation_id}</p>
                    {entry.duration_ms ? (
                      <p className="mt-0.5 text-xs text-slate-400">{entry.duration_ms}ms</p>
                    ) : null}
                  </button>
                ))}
                {auditEntries.length === 0 && auditState ? (
                  <EmptyState title="No entries" body="No audit entries match the current filter." />
                ) : null}
              </div>
            </div>
          </section>

          <section className="grid gap-4 self-start">
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Request payload</p>
              <pre className="code-panel mt-4">{prettyJson(selectedAuditEntry?.request_payload || null)}</pre>
            </section>
            <section className="surface-card p-5">
              <p className="eyebrow">Response payload</p>
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
                <EmptyState title="No benchmark loaded" body="Load the benchmark to inspect the evaluation summary." />
              </div>
            )}
          </section>
          {benchmark ? (
            <details className="surface-card px-6 py-5">
              <summary className="cursor-pointer text-sm font-semibold text-slate-700 marker:text-slate-400">
                Question-level results
              </summary>
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
        status: "supported", intent: "aggregate",
        source_relation: "safe.harmonized_observations_v1",
        selected_measures: ["yield"], selected_dimensions: ["variety"],
        filters: [
          { field_name: "variable", operator: "eq", value: "yield", source_text: "yield" },
          { field_name: "normalized_unit", operator: "eq", value: "kg/ha", source_text: "kg/ha" }
        ],
        aggregations: [{ function: "avg", field_name: "normalized_value", alias: "metric_value" }],
        grouping: ["variety"], ordering: [{ field_name: "variety", direction: "asc", source_text: "by variety" }],
        limit: 25, unit_handling: { mode: "canonical_normalized", normalized_unit: "kg/ha", note: null },
        ambiguity_flags: [], validation_notes: [], trace: [], target_measure: "yield", result_type: "aggregation"
      }
    },
    explain_metadata: { query: "yield units and quality flags", limit: 5 },
    retrieve_evidence: { query: "validation flags and yield units", limit: 5 }
  };
  return prettyJson(defaults[toolName] || {});
}

function MetricCard({ title, correct, total }: { title: string; correct: number; total: number }) {
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  const tone = pct >= 80 ? "text-emerald-700" : pct >= 60 ? "text-amber-700" : "text-rose-700";
  return (
    <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className={cn("mt-2 text-2xl font-semibold", tone)}>
        {correct}<span className="text-base text-slate-400">/{total}</span>
      </p>
      <p className="mt-0.5 text-xs text-slate-400">{pct}%</p>
    </div>
  );
}

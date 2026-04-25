"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { WorkflowStepper } from "../components/WorkflowStepper";
import type {
  AggregationItem,
  AggregationResponse,
  CanonicalMeasure,
  HarmonizedObservation,
  HarmonizedObservationResponse,
  QueryMetadata,
  ValidationStatus
} from "../lib/api_types";
import { API_BASE, formatNumber, readOnlyText, readProblemDetail, toErrorMessage } from "../lib/client";
import { primaryWorkflowSteps } from "../lib/workflow";

type WorkspaceFilters = {
  uploadSessionId: string;
  variable: CanonicalMeasure | "";
  validationStatus: ValidationStatus | "";
  search: string;
};

const DEFAULT_FILTERS: WorkspaceFilters = {
  uploadSessionId: "",
  variable: "",
  validationStatus: "",
  search: ""
};

const DEFAULT_COLUMNS = {
  observation_date: true,
  variable: true,
  normalized_value: true,
  variety: true,
  treatment: true,
  location: true,
  replicate: true,
  validation_status: true
};

const EXAMPLE_FILTERS = [
  { label: "Yield only", update: { variable: "yield" as CanonicalMeasure } },
  { label: "Warnings only", update: { validationStatus: "warning" as ValidationStatus } },
  { label: "Show all", update: { variable: "", validationStatus: "" as ValidationStatus | "" } }
];

export default function WorkspacePage() {
  return (
    <Suspense
      fallback={
        <section className="surface-card flex min-h-[320px] items-center justify-center px-6 py-10">
          <p className="text-sm font-medium text-slate-500">Loading workspace...</p>
        </section>
      }
    >
      <WorkspacePageContent />
    </Suspense>
  );
}

function WorkspacePageContent() {
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<WorkspaceFilters>(DEFAULT_FILTERS);
  const [metadata, setMetadata] = useState<QueryMetadata | null>(null);
  const [rows, setRows] = useState<HarmonizedObservation[]>([]);
  const [aggregationRows, setAggregationRows] = useState<AggregationItem[]>([]);
  const [selectedRow, setSelectedRow] = useState<HarmonizedObservation | null>(null);
  const [visibleColumns, setVisibleColumns] = useState<Record<string, boolean>>(DEFAULT_COLUMNS);
  const [loadingState, setLoadingState] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const uploadSessionId = searchParams.get("upload_session_id") || "";
    setFilters((current) => ({
      ...current,
      uploadSessionId
    }));
  }, [searchParams]);

  useEffect(() => {
    void loadWorkspaceData(filters);
  }, [filters.uploadSessionId, filters.variable, filters.validationStatus]);

  const filteredRows = useMemo(() => {
    const query = filters.search.trim().toLowerCase();
    if (!query) {
      return rows;
    }

    return rows.filter((row) =>
      [row.plot_id, row.variety, row.treatment, row.location, row.variable, row.validation_status]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    );
  }, [filters.search, rows]);

  const summary = useMemo(() => {
    const result = { valid: 0, warning: 0, invalid: 0 };
    for (const row of rows) {
      result[row.validation_status] += 1;
    }
    return result;
  }, [rows]);

  async function loadWorkspaceData(nextFilters: WorkspaceFilters): Promise<void> {
    setLoadingState("Loading committed data...");
    setError("");

    try {
      const rowParams = new URLSearchParams();
      rowParams.set("limit", "100");
      if (nextFilters.uploadSessionId) rowParams.set("upload_session_id", nextFilters.uploadSessionId);
      if (nextFilters.variable) rowParams.set("variable", nextFilters.variable);
      if (nextFilters.validationStatus) rowParams.set("validation_status", nextFilters.validationStatus);

      const aggregationParams = new URLSearchParams();
      aggregationParams.set("group_by", "validation_status");
      aggregationParams.set("metric", "count");
      aggregationParams.set("include_invalid", "true");
      if (nextFilters.uploadSessionId) aggregationParams.set("upload_session_id", nextFilters.uploadSessionId);
      if (nextFilters.variable) aggregationParams.set("variable", nextFilters.variable);

      const [metadataResponse, rowsResponse, aggregationResponse] = await Promise.all([
        fetch(`${API_BASE}/api/harmonized/query-metadata`),
        fetch(`${API_BASE}/api/harmonized/observations?${rowParams.toString()}`),
        fetch(`${API_BASE}/api/harmonized/aggregations?${aggregationParams.toString()}`)
      ]);

      if (!metadataResponse.ok) {
        throw new Error(await readProblemDetail(metadataResponse, "Failed to load query metadata."));
      }
      if (!rowsResponse.ok) {
        throw new Error(await readProblemDetail(rowsResponse, "Failed to load harmonized rows."));
      }
      if (!aggregationResponse.ok) {
        throw new Error(await readProblemDetail(aggregationResponse, "Failed to load summary."));
      }

      const metadataPayload = (await metadataResponse.json()) as QueryMetadata;
      const rowsPayload = (await rowsResponse.json()) as HarmonizedObservationResponse;
      const aggregationPayload = (await aggregationResponse.json()) as AggregationResponse;

      setMetadata(metadataPayload);
      setRows(rowsPayload.items || []);
      setAggregationRows(aggregationPayload.items || []);
      setSelectedRow(rowsPayload.items[0] || null);
      setLoadingState("Committed data loaded.");
    } catch (caught) {
      setMetadata(null);
      setRows([]);
      setAggregationRows([]);
      setSelectedRow(null);
      setError(toErrorMessage(caught, "Failed to load committed data."));
      setLoadingState("");
    }
  }

  return (
    <div className="grid gap-6">
      <section className="surface-card px-6 py-8 sm:px-8">
        <div className="grid gap-6 lg:grid-cols-[1.15fr,0.85fr]">
          <div className="space-y-5">
            <div className="space-y-3">
              <p className="eyebrow">Step 6</p>
              <h1 className="text-4xl font-semibold tracking-tight text-slate-950">Harmonized data workspace</h1>
              <p className="max-w-3xl text-base leading-7 text-slate-600">
                Browse committed observations, apply a few important filters and inspect the selected row in a dedicated detail panel.
              </p>
            </div>

            <WorkflowStepper steps={primaryWorkflowSteps()} activeKey="browse" />

            <div className="flex flex-wrap gap-3">
              <Link href="/upload" className="btn-ghost px-6">
                Upload another workbook
              </Link>
              <Link
                href={filters.uploadSessionId ? `/ai?upload_session_id=${encodeURIComponent(filters.uploadSessionId)}` : "/ai"}
                className="btn-primary px-6"
              >
                Continue to AI query
              </Link>
            </div>
          </div>

          <div className="surface-card-muted p-5">
            <p className="eyebrow">Current scope</p>
            <p className="mt-2 text-base leading-7 text-slate-700">
              {filters.uploadSessionId ? (
                <>
                  Viewing one committed upload:
                  <br />
                  <strong>{filters.uploadSessionId}</strong>
                </>
              ) : (
                <>Viewing all committed uploads.</>
              )}
            </p>
            {loadingState ? <p className="mt-3 text-sm text-slate-500">{loadingState}</p> : null}
          </div>
        </div>
      </section>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <section className="surface-card p-5">
        <div className="grid gap-4 lg:grid-cols-[1.1fr,0.9fr,0.9fr,1fr]">
          <label className="grid gap-2">
            <span className="text-sm font-medium text-slate-700">Upload session</span>
            <input
              className="input-shell"
              value={filters.uploadSessionId}
              onChange={(event) => setFilters((current) => ({ ...current, uploadSessionId: event.target.value }))}
              placeholder="Optional scope"
            />
          </label>

          <label className="grid gap-2">
            <span className="text-sm font-medium text-slate-700">Variable</span>
            <select
              className="input-shell"
              value={filters.variable}
              onChange={(event) => setFilters((current) => ({ ...current, variable: event.target.value as CanonicalMeasure | "" }))}
            >
              <option value="">All variables</option>
              {(metadata?.available_variables || []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-sm font-medium text-slate-700">Validation status</span>
            <select
              className="input-shell"
              value={filters.validationStatus}
              onChange={(event) =>
                setFilters((current) => ({ ...current, validationStatus: event.target.value as ValidationStatus | "" }))
              }
            >
              <option value="">All statuses</option>
              {(metadata?.supported_validation_statuses || []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-sm font-medium text-slate-700">Search in loaded rows</span>
            <input
              className="input-shell"
              value={filters.search}
              onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
              placeholder="Plot, variety, treatment, location..."
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {EXAMPLE_FILTERS.map((item) => (
            <button
              key={item.label}
              type="button"
              className="btn-ghost min-h-10 px-4"
              onClick={() =>
                setFilters((current) => ({
                  ...current,
                  variable: (item.update.variable as CanonicalMeasure | "") ?? current.variable,
                  validationStatus: (item.update.validationStatus as ValidationStatus | "") ?? current.validationStatus
                }))
              }
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="surface-card-muted grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
          <p className="text-sm font-medium text-slate-500">Loaded rows</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{rows.length}</p>
        </div>
        <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
          <p className="text-sm font-medium text-slate-500">Visible after search</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{filteredRows.length}</p>
        </div>
        <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
          <p className="text-sm font-medium text-slate-500">Warnings</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{summary.warning}</p>
        </div>
        <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
          <p className="text-sm font-medium text-slate-500">Invalid</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{summary.invalid}</p>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <section className="surface-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Data browser</p>
              <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Committed observations</h2>
            </div>

            <details className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700">
              <summary className="cursor-pointer font-semibold">Columns</summary>
              <div className="mt-3 grid gap-2">
                {Object.keys(DEFAULT_COLUMNS).map((column) => (
                  <label key={column} className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={visibleColumns[column]}
                      onChange={(event) =>
                        setVisibleColumns((current) => ({ ...current, [column]: event.target.checked }))
                      }
                    />
                    {column}
                  </label>
                ))}
              </div>
            </details>
          </div>

          <div className="mt-5">
            {filteredRows.length === 0 ? (
              <EmptyState
                title="No rows for the current scope"
                body="Change the filters or commit harmonized rows from the upload workflow first."
              />
            ) : (
              <div className="overflow-x-auto rounded-[1.25rem] border border-slate-200 bg-white">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-left text-slate-600">
                    <tr>
                      {visibleColumns.observation_date ? <th className="px-4 py-3 font-semibold">Date</th> : null}
                      {visibleColumns.variable ? <th className="px-4 py-3 font-semibold">Variable</th> : null}
                      {visibleColumns.normalized_value ? <th className="px-4 py-3 font-semibold">Value</th> : null}
                      {visibleColumns.variety ? <th className="px-4 py-3 font-semibold">Variety</th> : null}
                      {visibleColumns.treatment ? <th className="px-4 py-3 font-semibold">Treatment</th> : null}
                      {visibleColumns.location ? <th className="px-4 py-3 font-semibold">Location</th> : null}
                      {visibleColumns.replicate ? <th className="px-4 py-3 font-semibold">Replicate</th> : null}
                      {visibleColumns.validation_status ? <th className="px-4 py-3 font-semibold">Status</th> : null}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredRows.map((row) => (
                      <tr
                        key={`${row.upload_session_id}-${row.source_sheet}-${row.source_row_index}-${row.source_column}`}
                        className="cursor-pointer hover:bg-cyan-50/60"
                        onClick={() => setSelectedRow(row)}
                      >
                        {visibleColumns.observation_date ? <td className="px-4 py-3">{readOnlyText(row.observation_date)}</td> : null}
                        {visibleColumns.variable ? <td className="px-4 py-3 font-medium text-slate-900">{readOnlyText(row.variable)}</td> : null}
                        {visibleColumns.normalized_value ? (
                          <td className="px-4 py-3">
                            {formatNumber(row.normalized_value ?? row.value)} {row.normalized_unit ?? row.unit ?? ""}
                          </td>
                        ) : null}
                        {visibleColumns.variety ? <td className="px-4 py-3">{readOnlyText(row.variety)}</td> : null}
                        {visibleColumns.treatment ? <td className="px-4 py-3">{readOnlyText(row.treatment)}</td> : null}
                        {visibleColumns.location ? <td className="px-4 py-3">{readOnlyText(row.location)}</td> : null}
                        {visibleColumns.replicate ? <td className="px-4 py-3">{readOnlyText(row.replicate)}</td> : null}
                        {visibleColumns.validation_status ? <td className="px-4 py-3">{row.validation_status}</td> : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <div className="grid gap-6">
          <section className="surface-card p-5">
            <p className="eyebrow">Selected row</p>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Details</h2>
            {selectedRow ? (
              <div className="mt-5 grid gap-3">
                <Field label="Date" value={readOnlyText(selectedRow.observation_date)} />
                <Field label="Plot" value={readOnlyText(selectedRow.plot_id)} />
                <Field label="Variety" value={readOnlyText(selectedRow.variety)} />
                <Field label="Treatment" value={readOnlyText(selectedRow.treatment)} />
                <Field label="Location" value={readOnlyText(selectedRow.location)} />
                <Field label="Replicate" value={readOnlyText(selectedRow.replicate)} />
                <Field label="Variable" value={readOnlyText(selectedRow.variable)} />
                <Field
                  label="Source value"
                  value={`${formatNumber(selectedRow.value)} ${selectedRow.unit ?? ""}`.trim()}
                />
                <Field
                  label="Normalized value"
                  value={`${formatNumber(selectedRow.normalized_value)} ${selectedRow.normalized_unit ?? ""}`.trim()}
                />
                <Field label="Status" value={selectedRow.validation_status} />
                <Field label="Lineage" value={`${selectedRow.source_sheet}:${selectedRow.source_row_index} · ${selectedRow.source_column}`} />
              </div>
            ) : (
              <EmptyState title="No row selected" body="Select a row from the table to inspect its harmonized details." />
            )}
          </section>

          <section className="surface-card-muted p-5">
            <p className="eyebrow">Validation summary</p>
            <div className="mt-4 grid gap-3">
              {aggregationRows.map((item, index) => (
                <div key={`${item.group_value}-${index}`} className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
                  <p className="text-sm font-medium text-slate-500">{item.group_value || "n/a"}</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-900">{item.metric_value}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-900">{value}</p>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { EmptyState } from "../../components/EmptyState";
import { Notice } from "../../components/Notice";
import { WorkflowStepper } from "../../components/WorkflowStepper";
import { API_BASE, cn, readOnlyText, readProblemDetail, toErrorMessage } from "../../lib/client";
import { pushRecentUpload } from "../../lib/recent_uploads";
import { uploadWorkflowSteps } from "../../lib/workflow";
import {
  blockWarningCount,
  clonePreview,
  countByRole,
  effectiveType,
  extractEditPayload,
  formatBytes,
  measureUnitOptions,
  normalizeUploadId,
  stableEditPayload,
  summarizeQuality,
  targetUnitForMeasure,
  updateRoleDefaults
} from "./page_helpers";
import type {
  CanonicalDimension,
  CanonicalMeasure,
  ColumnSuggestion,
  ColumnType,
  CommitResponse,
  PreviewBlock,
  PreviewPayload,
  QualityObservationResponse,
  QualitySummary,
  RawArtifact,
  SemanticRole,
  SupportedUnit,
  UploadDetailResponse,
  UploadPreviewResponse,
  UploadStatus
} from "./page_types";

type StageKey = "review" | "mapping" | "validation" | "commit";

type DraftIssue = {
  level: "error" | "warning";
  blockId: string;
  column?: string;
  message: string;
};

const STAGE_META: Record<StageKey, { title: string; subtitle: string; primaryLabel: string }> = {
  review: {
    title: "Review detected blocks",
    subtitle: "Check the parsed sheet structure and confirm that the detected data looks correct.",
    primaryLabel: "Continue to mapping"
  },
  mapping: {
    title: "Map semantic meaning",
    subtitle: "Assign each column a clear role and only fill in the fields that are actually needed.",
    primaryLabel: "Continue to validation"
  },
  validation: {
    title: "Resolve blocking issues",
    subtitle: "Focus only on what prevents a clean commit. Warnings stay visible, but secondary details remain collapsed.",
    primaryLabel: "Continue to commit"
  },
  commit: {
    title: "Commit summary",
    subtitle: "Review what will be written into the harmonized layer, then commit once.",
    primaryLabel: "Commit harmonized data"
  }
};

function StageTabs({
  activeStage,
  onSelectStage
}: {
  activeStage: StageKey;
  onSelectStage: (stage: StageKey) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {(Object.keys(STAGE_META) as StageKey[]).map((stage) => (
        <button
          key={stage}
          type="button"
          className={cn(
            "rounded-full border px-4 py-2 text-sm font-semibold transition",
            activeStage === stage
              ? "border-cyan-200 bg-cyan-50 text-cyan-900"
              : "border-slate-200 bg-white text-slate-600 hover:border-cyan-200"
          )}
          onClick={() => onSelectStage(stage)}
        >
          {STAGE_META[stage].title}
        </button>
      ))}
    </div>
  );
}

function SummaryCard({ label, value, emphasis = false }: { label: string; value: ReactNode; emphasis?: boolean }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={cn("mt-2 text-lg font-semibold", emphasis ? "text-slate-950" : "text-slate-900")}>{value}</p>
    </div>
  );
}

function DataPreviewTable({ block }: { block: PreviewBlock }) {
  if (block.sample_rows.length === 0) {
    return <EmptyState title="No preview rows" body="This block does not expose sample rows for review." />;
  }

  return (
    <div className="overflow-x-auto rounded-[1.25rem] border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            {block.headers.map((header) => (
              <th key={header} className="px-4 py-3 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {block.sample_rows.map((row, index) => (
            <tr key={`${block.block_id}-${index}`}>
              {block.headers.map((header) => (
                <td key={`${index}-${header}`} className="px-4 py-3 text-slate-700">
                  {String(row[header] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MappingRow({
  blockId,
  item,
  onUpdate
}: {
  blockId: string;
  item: ColumnSuggestion;
  onUpdate: (
    blockId: string,
    columnName: string,
    updater: (column: ColumnSuggestion) => ColumnSuggestion
  ) => void;
}) {
  return (
    <article className="rounded-[1.25rem] border border-slate-200 bg-white p-4">
      <div className="grid gap-4 lg:grid-cols-[1fr,1.2fr]">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">{item.column}</h3>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-600">
              {effectiveType(item)}
            </span>
          </div>
          <p className="text-sm text-slate-600">
            Suggested type: {item.suggested}. Current role: <strong>{item.semantic_role}</strong>
          </p>
          {item.warnings.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {item.warnings.map((warning) => (
                <span key={`${item.column}-${warning}`} className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
                  {warning}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="grid gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Role</span>
            <select
              className="input-shell"
              value={item.semantic_role}
              onChange={(event) =>
                onUpdate(blockId, item.column, (current) => updateRoleDefaults(current, event.target.value as SemanticRole))
              }
            >
              <option value="ignore">Ignore</option>
              <option value="date">Date</option>
              <option value="dimension">Dimension</option>
              <option value="measure">Measure</option>
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Type</span>
            <select
              className="input-shell"
              value={item.type_override ?? ""}
              onChange={(event) =>
                onUpdate(blockId, item.column, (current) => ({
                  ...current,
                  type_override: event.target.value === "" ? null : (event.target.value as ColumnType)
                }))
              }
            >
              <option value="">Use inferred</option>
              <option value="text">Text</option>
              <option value="numeric">Numeric</option>
              <option value="date">Date</option>
            </select>
          </label>

          <label className="grid gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Meaning</span>
            {item.semantic_role === "measure" ? (
              <select
                className="input-shell"
                value={item.canonical_measure ?? ""}
                onChange={(event) =>
                  onUpdate(blockId, item.column, (current) => ({
                    ...current,
                    canonical_measure:
                      event.target.value === "" ? null : (event.target.value as CanonicalMeasure)
                  }))
                }
              >
                <option value="">Select measure</option>
                <option value="yield">yield</option>
                <option value="moisture">moisture</option>
                <option value="plant_height">plant_height</option>
              </select>
            ) : item.semantic_role === "dimension" ? (
              <select
                className="input-shell"
                value={item.canonical_dimension ?? ""}
                onChange={(event) =>
                  onUpdate(blockId, item.column, (current) => ({
                    ...current,
                    canonical_dimension:
                      event.target.value === "" ? null : (event.target.value as CanonicalDimension)
                  }))
                }
              >
                <option value="">Select dimension</option>
                <option value="plot_id">plot_id</option>
                <option value="variety">variety</option>
                <option value="treatment">treatment</option>
                <option value="location">location</option>
                <option value="replicate">replicate</option>
              </select>
            ) : (
              <div className="input-shell flex items-center text-slate-500">
                {item.semantic_role === "date" ? "Observation date" : "Not required"}
              </div>
            )}
          </label>

          <label className="grid gap-2">
            <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Unit</span>
            {item.semantic_role === "measure" && item.canonical_measure ? (
              <select
                className="input-shell"
                value={item.unit ?? ""}
                onChange={(event) =>
                  onUpdate(blockId, item.column, (current) => ({
                    ...current,
                    unit: event.target.value === "" ? null : (event.target.value as SupportedUnit)
                  }))
                }
              >
                <option value="">Select unit</option>
                {measureUnitOptions(item.canonical_measure).map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            ) : (
              <div className="input-shell flex items-center text-slate-500">
                {item.semantic_role === "measure" ? "Select meaning first" : "Not required"}
              </div>
            )}
          </label>
        </div>
      </div>

      {item.semantic_role === "measure" && item.canonical_measure ? (
        <p className="mt-3 text-sm text-slate-600">
          Canonical unit: <strong>{targetUnitForMeasure(item.canonical_measure) || "n/a"}</strong>
        </p>
      ) : null}
    </article>
  );
}

function YearOverridePanel({
  blocks,
  yearOverride,
  onUpdate
}: {
  blocks: PreviewBlock[];
  yearOverride: number | null;
  onUpdate: (value: number | null) => void;
}) {
  const blocksNeedingYear = blocks.filter((block) => {
    const hasDateColumn = block.type_suggestions.some((s) => s.semantic_role === "date");
    return !hasDateColumn;
  });

  if (blocksNeedingYear.length === 0) {
    return null;
  }

  const inferredYears = [...new Set(blocksNeedingYear.map((b) => b.inferred_year).filter((y): y is number => y !== null))];
  const effectiveYear = yearOverride ?? (inferredYears.length === 1 ? inferredYears[0] : null);

  return (
    <div className="mt-5 rounded-[1.25rem] border border-cyan-200 bg-cyan-50 px-4 py-4">
      <p className="text-sm font-semibold text-cyan-900">Observation year</p>
      <p className="mt-1 text-sm text-cyan-800">
        {inferredYears.length > 0
          ? `Year detected from document: ${inferredYears.join(", ")}. You can override it below.`
          : "No year was found in the document or filename. Set a year override to proceed."}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="grid gap-1">
          <span className="text-xs font-medium uppercase tracking-[0.16em] text-cyan-700">Year override</span>
          <input
            type="number"
            min={1900}
            max={2100}
            placeholder={effectiveYear != null ? String(effectiveYear) : "e.g. 2007"}
            value={yearOverride ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (!raw) {
                onUpdate(null);
              } else {
                const parsed = parseInt(raw, 10);
                if (!isNaN(parsed) && parsed >= 1900 && parsed <= 2100) {
                  onUpdate(parsed);
                }
              }
            }}
            className="input-shell w-32"
          />
        </label>
        {yearOverride !== null ? (
          <button
            type="button"
            className="mt-4 text-xs font-medium text-cyan-700 underline"
            onClick={() => onUpdate(null)}
          >
            Clear override
          </button>
        ) : null}
      </div>
      {effectiveYear !== null ? (
        <p className="mt-2 text-xs text-cyan-700">
          Observations without a row-level date will use <strong>{effectiveYear}</strong> as the observation year.
        </p>
      ) : null}
    </div>
  );
}

function UploadWorkflowPageContent() {
  const params = useParams<{ id?: string | string[] }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const uploadId = normalizeUploadId(params?.id);

  const [savedPreview, setSavedPreview] = useState<PreviewPayload | null>(null);
  const [draftPreview, setDraftPreview] = useState<PreviewPayload | null>(null);
  const [rawArtifact, setRawArtifact] = useState<RawArtifact | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("preview_ready");
  const [selectedBlockId, setSelectedBlockId] = useState("");
  const [qualitySummary, setQualitySummary] = useState<QualitySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState("");
  const [commitState, setCommitState] = useState("");

  const currentStage = useMemo<StageKey>(() => {
    const rawStage = searchParams.get("stage");
    if (rawStage === "mapping" || rawStage === "validation" || rawStage === "commit") {
      return rawStage;
    }
    return "review";
  }, [searchParams]);

  useEffect(() => {
    if (!uploadId) {
      setLoading(false);
      setError("Upload id is missing.");
      return;
    }
    const currentUploadId = uploadId;

    async function bootstrap(): Promise<void> {
      setLoading(true);
      setError("");

      try {
        const [previewResponse, uploadResponse] = await Promise.all([
          fetch(`${API_BASE}/uploads/${currentUploadId}/preview`),
          fetch(`${API_BASE}/uploads/${currentUploadId}`)
        ]);

        if (!previewResponse.ok) {
          throw new Error(await readProblemDetail(previewResponse, "Failed to load preview."));
        }
        if (!uploadResponse.ok) {
          throw new Error(await readProblemDetail(uploadResponse, "Failed to load upload detail."));
        }

        const previewPayload = (await previewResponse.json()) as UploadPreviewResponse;
        const uploadPayload = (await uploadResponse.json()) as UploadDetailResponse;
        const nextPreview = previewPayload.preview || null;

        setSavedPreview(nextPreview);
        setDraftPreview(nextPreview ? clonePreview(nextPreview) : null);
        setRawArtifact(previewPayload.raw_artifact || null);
        setUploadStatus(uploadPayload.status);

        if (nextPreview?.file_name) {
          pushRecentUpload({ id: currentUploadId, filename: nextPreview.file_name });
        }

        const summaryResponse = await fetch(
          `${API_BASE}/api/harmonized/observations?upload_session_id=${encodeURIComponent(currentUploadId)}&limit=1000`
        );
        if (summaryResponse.ok) {
          const summaryPayload = (await summaryResponse.json()) as QualityObservationResponse;
          setQualitySummary(summaryPayload.items.length > 0 ? summarizeQuality(summaryPayload.items) : null);
        } else {
          setQualitySummary(null);
        }
      } catch (caught) {
        setError(toErrorMessage(caught, "Failed to load upload workflow."));
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
  }, [uploadId]);

  useEffect(() => {
    const blocks = draftPreview?.blocks || [];
    if (blocks.length === 0) {
      setSelectedBlockId("");
      return;
    }

    if (!blocks.some((block) => block.block_id === selectedBlockId)) {
      setSelectedBlockId(blocks[0].block_id);
    }
  }, [draftPreview, selectedBlockId]);

  const selectedBlock = useMemo(() => {
    return draftPreview?.blocks.find((block) => block.block_id === selectedBlockId) || draftPreview?.blocks[0] || null;
  }, [draftPreview, selectedBlockId]);

  const isDirty = useMemo(() => {
    if (!savedPreview || !draftPreview) {
      return false;
    }
    return JSON.stringify(stableEditPayload(savedPreview)) !== JSON.stringify(stableEditPayload(draftPreview));
  }, [draftPreview, savedPreview]);

  const mappingSummary = useMemo(() => {
    const blocks = draftPreview?.blocks || [];
    let measures = 0;
    let dimensions = 0;
    let dates = 0;
    let ignored = 0;
    let warnings = 0;

    for (const block of blocks) {
      const counts = countByRole(block);
      measures += counts.measure;
      dimensions += counts.dimension;
      dates += counts.date;
      ignored += counts.ignore;
      warnings += blockWarningCount(block);
    }

    return { measures, dimensions, dates, ignored, warnings };
  }, [draftPreview]);

  const issues = useMemo(
    () => buildDraftIssues(draftPreview, draftPreview?.year_override ?? null),
    [draftPreview]
  );

  const commitEstimate = useMemo(() => estimateCommitRows(draftPreview), [draftPreview]);

  function goToStage(stage: StageKey): void {
    const currentUploadId = uploadId;
    if (!currentUploadId) {
      return;
    }
    router.replace(`/uploads/${encodeURIComponent(currentUploadId)}?stage=${stage}`);
  }

  function updateDraftColumn(
    blockId: string,
    columnName: string,
    updater: (column: ColumnSuggestion) => ColumnSuggestion
  ): void {
    setDraftPreview((current) => {
      if (!current) {
        return current;
      }

      const next = clonePreview(current);
      const block = next.blocks.find((item) => item.block_id === blockId);
      const column = block?.type_suggestions.find((item) => item.column === columnName);
      if (!block || !column) {
        return current;
      }

      Object.assign(column, updater(column));
      return next;
    });
    setSaveState("");
    setCommitState("");
  }

  function updateYearOverride(value: number | null): void {
    setDraftPreview((current) => {
      if (!current) return current;
      return { ...current, year_override: value };
    });
    setSaveState("");
    setCommitState("");
  }

  async function persistDraft(): Promise<boolean> {
    const currentUploadId = uploadId;
    if (!currentUploadId || !draftPreview) {
      return false;
    }

    setSaveState("Saving draft...");
    try {
      const response = await fetch(`${API_BASE}/uploads/${currentUploadId}/edits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(extractEditPayload(draftPreview))
      });

      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Failed to save edits."));
      }

      const payload = (await response.json()) as UploadPreviewResponse;
      const nextPreview = payload.preview || draftPreview;
      setSavedPreview(nextPreview);
      setDraftPreview(clonePreview(nextPreview));
      setSaveState("Draft saved.");
      return true;
    } catch (caught) {
      setSaveState(toErrorMessage(caught, "Failed to save edits."));
      return false;
    }
  }

  async function continueFromCurrentStage(): Promise<void> {
    if (currentStage === "review") {
      goToStage("mapping");
      return;
    }

    if (currentStage === "mapping") {
      const saved = isDirty ? await persistDraft() : true;
      if (saved) {
        goToStage("validation");
      }
      return;
    }

    if (currentStage === "validation") {
      if (issues.errors.length > 0) {
        setCommitState("Resolve blocking issues before continuing.");
        return;
      }
      const saved = isDirty ? await persistDraft() : true;
      if (saved) {
        goToStage("commit");
      }
      return;
    }

    await commitUpload();
  }

  async function commitUpload(): Promise<void> {
    const currentUploadId = uploadId;
    if (!currentUploadId) {
      return;
    }

    if (issues.errors.length > 0) {
      setCommitState("Resolve blocking issues before commit.");
      goToStage("validation");
      return;
    }

    if (isDirty) {
      const saved = await persistDraft();
      if (!saved) {
        setCommitState("Commit stopped because saving failed.");
        return;
      }
    }

    setCommitState("Committing...");
    try {
      const response = await fetch(`${API_BASE}/uploads/${currentUploadId}/commit`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Commit failed."));
      }

      const result = (await response.json()) as CommitResponse;
      setUploadStatus(result.status);
      setCommitState(`Committed ${result.harmonized_rows} rows.`);
      goToStage("commit");

      const summaryResponse = await fetch(
        `${API_BASE}/api/harmonized/observations?upload_session_id=${encodeURIComponent(currentUploadId)}&limit=1000`
      );
      if (summaryResponse.ok) {
        const summaryPayload = (await summaryResponse.json()) as QualityObservationResponse;
        setQualitySummary(summaryPayload.items.length > 0 ? summarizeQuality(summaryPayload.items) : null);
      }
    } catch (caught) {
      setCommitState(toErrorMessage(caught, "Commit failed."));
    }
  }

  if (loading) {
    return (
      <section className="surface-card flex min-h-[320px] items-center justify-center px-6 py-10">
        <p className="text-sm font-medium text-slate-500">Loading upload workflow...</p>
      </section>
    );
  }

  if (error || !draftPreview) {
    return (
      <section className="surface-card px-6 py-8">
        <Notice tone="error" title="Upload workflow failed">
          {error || "No preview data was found for this upload."}
        </Notice>
        <div className="mt-6">
          <Link href="/upload" className="btn-primary px-6">
            Back to upload
          </Link>
        </div>
      </section>
    );
  }

  const selectedStage = STAGE_META[currentStage];

  return (
    <div className="grid gap-6">
      <section className="surface-card px-6 py-7 sm:px-8">
        <div className="space-y-5">
          <div className="space-y-3">
            <p className="eyebrow">Guided workflow</p>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">{selectedStage.title}</h1>
            <p className="max-w-3xl text-sm leading-7 text-slate-600 sm:text-base">{selectedStage.subtitle}</p>
          </div>

          <WorkflowStepper steps={uploadWorkflowSteps(uploadId)} activeKey={currentStage} />
          <StageTabs activeStage={currentStage} onSelectStage={goToStage} />
        </div>
      </section>

      <section className="surface-card-muted grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryCard label="File" value={draftPreview.file_name} emphasis />
        <SummaryCard label="Blocks" value={draftPreview.block_count} />
        <SummaryCard label="Measures" value={mappingSummary.measures} />
        <SummaryCard label="Blocking issues" value={issues.errors.length} />
        <SummaryCard label="Status" value={uploadStatus} />
      </section>

      {saveState ? <Notice tone="info">{saveState}</Notice> : null}
      {commitState ? <Notice tone={uploadStatus === "committed" ? "success" : "warning"}>{commitState}</Notice> : null}

      {currentStage === "review" ? (
        <div className="grid gap-6 lg:grid-cols-[280px,minmax(0,1fr)]">
          <section className="surface-card-muted p-5">
            <p className="eyebrow">Detected blocks</p>
            <div className="mt-4 grid gap-3">
              {draftPreview.blocks.map((block) => (
                <button
                  key={block.block_id}
                  type="button"
                  onClick={() => setSelectedBlockId(block.block_id)}
                  className={cn(
                    "rounded-[1.25rem] border px-4 py-4 text-left transition",
                    selectedBlock?.block_id === block.block_id
                      ? "border-cyan-200 bg-cyan-50"
                      : "border-slate-200 bg-white hover:border-cyan-200"
                  )}
                >
                  <p className="font-semibold text-slate-900">{block.block_id}</p>
                  <p className="mt-1 text-sm text-slate-600">{block.sheet || "n/a"} · {block.range || "n/a"}</p>
                  <p className="mt-2 text-sm text-slate-500">{block.type_suggestions.length} columns</p>
                  {block.inferred_year != null ? (
                    <p className="mt-1 text-xs font-medium text-cyan-700">Year: {block.inferred_year}</p>
                  ) : null}
                </button>
              ))}
            </div>
          </section>

          <div className="grid gap-6">
            {selectedBlock ? (
              <>
                <section className="surface-card p-5">
                  <p className="eyebrow">Preview</p>
                  <h2 className="text-xl font-semibold tracking-tight text-slate-950">Sample rows</h2>
                  <div className="mt-5">
                    <DataPreviewTable block={selectedBlock} />
                  </div>
                </section>

                <section className="surface-card p-5">
                  <p className="eyebrow">What was detected</p>
                  <div className="mt-4 grid gap-4 sm:grid-cols-4">
                    <SummaryCard label="Measures" value={countByRole(selectedBlock).measure} />
                    <SummaryCard label="Dimensions" value={countByRole(selectedBlock).dimension} />
                    <SummaryCard label="Dates" value={countByRole(selectedBlock).date} />
                    <SummaryCard label="Warnings" value={blockWarningCount(selectedBlock)} />
                  </div>
                </section>
              </>
            ) : (
              <EmptyState title="No block selected" body="Select a detected block to review its preview rows." />
            )}
          </div>
        </div>
      ) : null}

      {currentStage === "mapping" ? (
        <div className="grid gap-6">
          {draftPreview.blocks.length > 1 ? (
            <section className="surface-card-muted p-5">
              <p className="eyebrow">Choose block</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {draftPreview.blocks.map((block) => (
                  <button
                    key={block.block_id}
                    type="button"
                    className={cn(
                      "rounded-full border px-4 py-2 text-sm font-semibold transition",
                      selectedBlock?.block_id === block.block_id
                        ? "border-cyan-200 bg-cyan-50 text-cyan-900"
                        : "border-slate-200 bg-white text-slate-600 hover:border-cyan-200"
                    )}
                    onClick={() => setSelectedBlockId(block.block_id)}
                  >
                    {block.block_id}
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {selectedBlock ? (
            <section className="surface-card p-5">
              <div className="space-y-2">
                <p className="eyebrow">Mapping</p>
                <h2 className="text-xl font-semibold tracking-tight text-slate-950">{selectedBlock.block_id}</h2>
                <p className="text-sm text-slate-600">Only the essential mapping controls are shown here.</p>
              </div>

              <div className="mt-5 grid gap-4">
                {selectedBlock.type_suggestions.map((item) => (
                  <MappingRow key={`${selectedBlock.block_id}-${item.column}`} blockId={selectedBlock.block_id} item={item} onUpdate={updateDraftColumn} />
                ))}
              </div>
            </section>
          ) : (
            <EmptyState title="No block selected" body="Select a detected block to map its columns." />
          )}
        </div>
      ) : null}

      {currentStage === "validation" ? (
        <div className="grid gap-6 lg:grid-cols-[1fr,0.9fr]">
          <section className="surface-card p-5">
            <p className="eyebrow">Blocking issues</p>
            <h2 className="text-xl font-semibold tracking-tight text-slate-950">What must be fixed before commit</h2>
            <YearOverridePanel
              blocks={draftPreview.blocks}
              yearOverride={draftPreview.year_override ?? null}
              onUpdate={updateYearOverride}
            />
            <div className="mt-5">
              {issues.errors.length === 0 ? (
                <Notice tone="success" title="Ready to continue">
                  No blocking mapping issues were found in the current draft.
                </Notice>
              ) : (
                <div className="grid gap-3">
                  {issues.errors.map((issue, index) => (
                    <div key={`${issue.blockId}-${issue.column || "global"}-${index}`} className="rounded-[1.25rem] border border-rose-200 bg-rose-50 px-4 py-4">
                      <p className="font-semibold text-rose-900">
                        {issue.blockId}
                        {issue.column ? ` · ${issue.column}` : ""}
                      </p>
                      <p className="mt-1 text-sm text-rose-800">{issue.message}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="surface-card-muted p-5">
            <p className="eyebrow">Warnings</p>
            <h2 className="text-xl font-semibold tracking-tight text-slate-950">Non-blocking observations</h2>
            <div className="mt-5">
              {issues.warnings.length === 0 ? (
                <EmptyState title="No warnings" body="The current draft does not expose extra parser or mapping warnings." />
              ) : (
                <div className="grid gap-3">
                  {issues.warnings.map((issue, index) => (
                    <div key={`${issue.blockId}-${issue.column || "global"}-${index}`} className="rounded-[1.25rem] border border-amber-200 bg-white px-4 py-4">
                      <p className="font-semibold text-slate-900">
                        {issue.blockId}
                        {issue.column ? ` · ${issue.column}` : ""}
                      </p>
                      <p className="mt-1 text-sm text-slate-600">{issue.message}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {currentStage === "commit" ? (
        <div className="grid gap-6 lg:grid-cols-[1fr,0.85fr]">
          <section className="surface-card p-5">
            <p className="eyebrow">Commit summary</p>
            <h2 className="text-xl font-semibold tracking-tight text-slate-950">What will be written</h2>
            <YearOverridePanel
              blocks={draftPreview.blocks}
              yearOverride={draftPreview.year_override ?? null}
              onUpdate={updateYearOverride}
            />
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <SummaryCard label="Estimated observations" value={commitEstimate} emphasis />
              <SummaryCard label="Measure columns" value={mappingSummary.measures} />
              <SummaryCard label="Dimension columns" value={mappingSummary.dimensions} />
              <SummaryCard label="Warning count" value={issues.warnings.length} />
            </div>

            {qualitySummary ? (
              <div className="mt-5 grid gap-4 sm:grid-cols-4">
                <SummaryCard label="Committed total" value={qualitySummary.total} />
                <SummaryCard label="Valid" value={qualitySummary.valid} />
                <SummaryCard label="Warning" value={qualitySummary.warning} />
                <SummaryCard label="Invalid" value={qualitySummary.invalid} />
              </div>
            ) : null}

            {uploadStatus === "committed" ? (
              <Notice tone="success" title="Already committed">
                This upload already has harmonized rows. You can continue to the workspace or the AI screen.
              </Notice>
            ) : issues.errors.length > 0 ? (
              <Notice tone="warning" title="Commit blocked">
                Resolve the blocking issues on the validation step before committing.
              </Notice>
            ) : (
              <Notice tone="info" title="Ready to commit">
                The draft is valid enough for the harmonized write step.
              </Notice>
            )}
          </section>

          <section className="surface-card-muted p-5">
            <p className="eyebrow">Advanced details</p>
            <div className="mt-4 grid gap-3">
              <details className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
                <summary className="cursor-pointer font-semibold text-slate-900">Raw artifact metadata</summary>
                {rawArtifact ? (
                  <div className="mt-4 grid gap-3 text-sm text-slate-600">
                    <p>Filename: {rawArtifact.original_filename}</p>
                    <p>Size: {formatBytes(rawArtifact.file_size_bytes)}</p>
                    <p>Parser: {rawArtifact.parser_version}</p>
                    <p>Uploaded at: {new Date(rawArtifact.uploaded_at).toLocaleString("en-US")}</p>
                    <p className="break-all">SHA-256: {rawArtifact.file_hash_sha256}</p>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">No raw artifact metadata available.</p>
                )}
              </details>

              <details className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4">
                <summary className="cursor-pointer font-semibold text-slate-900">Sheet manifest</summary>
                {rawArtifact?.sheet_manifest?.length ? (
                  <div className="mt-4 grid gap-3">
                    {rawArtifact.sheet_manifest.map((sheet) => (
                      <div key={`${sheet.sheet_index}-${sheet.sheet_name}`} className="rounded-[1rem] border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                        <p className="font-semibold text-slate-900">{sheet.sheet_name}</p>
                        <p className="mt-1">
                          {sheet.row_count} rows · {sheet.max_column_count} max columns · {sheet.detected_block_count} blocks
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">No sheet manifest available.</p>
                )}
              </details>
            </div>
          </section>
        </div>
      ) : null}

      <section className="surface-card sticky bottom-4 z-20 px-5 py-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-500">
            {isDirty ? "You have unsaved changes." : "Your current draft is saved."}
          </div>

          <div className="flex flex-wrap gap-3">
            {currentStage !== "review" ? (
              <button
                type="button"
                className="btn-ghost px-5"
                onClick={() => goToStage((["review", "mapping", "validation", "commit"][
                  Math.max((["review", "mapping", "validation", "commit"] as StageKey[]).indexOf(currentStage) - 1, 0)
                ]) as StageKey)}
              >
                Back
              </button>
            ) : null}
            <button type="button" className="btn-ghost px-5" onClick={() => void persistDraft()} disabled={!isDirty}>
              Save draft
            </button>
            {uploadStatus === "committed" ? (
              <>
                <Link href={`/workspace?upload_session_id=${encodeURIComponent(uploadId || "")}`} className="btn-primary px-5">
                  Open workspace
                </Link>
                <Link href={`/ai?upload_session_id=${encodeURIComponent(uploadId || "")}`} className="btn-ghost px-5">
                  Open AI query
                </Link>
              </>
            ) : (
              <button type="button" className="btn-primary px-5" onClick={() => void continueFromCurrentStage()}>
                {selectedStage.primaryLabel}
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function blockEffectiveYear(block: PreviewBlock, yearOverride: number | null): number | null {
  return yearOverride ?? block.inferred_year ?? null;
}

function buildDraftIssues(
  preview: PreviewPayload | null,
  yearOverride: number | null = null
): { errors: DraftIssue[]; warnings: DraftIssue[] } {
  const errors: DraftIssue[] = [];
  const warnings: DraftIssue[] = [];

  for (const block of preview?.blocks || []) {
    const dateColumns = block.type_suggestions.filter((item) => item.semantic_role === "date");
    if (dateColumns.length > 1) {
      errors.push({
        level: "error",
        blockId: block.block_id,
        message: "Only one column can be marked as date in a single block."
      });
    }

    const hasDateColumn = dateColumns.length > 0;
    if (!hasDateColumn && blockEffectiveYear(block, yearOverride) === null) {
      errors.push({
        level: "error",
        blockId: block.block_id,
        message:
          "No observation year available. Either add a date column or set a year override — the data cannot be committed without a date."
      });
    }

    for (const item of block.type_suggestions) {
      if (item.semantic_role === "measure") {
        if (effectiveType(item) !== "numeric") {
          errors.push({
            level: "error",
            blockId: block.block_id,
            column: item.column,
            message: "Measure columns must use a numeric type."
          });
        }
        if (!item.canonical_measure) {
          warnings.push({
            level: "warning",
            blockId: block.block_id,
            column: item.column,
            message: "No canonical measure selected — column will be stored under its raw name."
          });
        }
        if (item.canonical_measure && !item.unit) {
          warnings.push({
            level: "warning",
            blockId: block.block_id,
            column: item.column,
            message: "No source unit selected — value will be stored without unit normalisation."
          });
        }
      }

      if (item.semantic_role === "dimension" && !item.canonical_dimension) {
        warnings.push({
          level: "warning",
          blockId: block.block_id,
          column: item.column,
          message: "No canonical dimension selected — values will be stored under the raw column name."
        });
      }

      if (item.semantic_role === "date" && effectiveType(item) !== "date") {
        errors.push({
          level: "error",
          blockId: block.block_id,
          column: item.column,
          message: "Date columns must use the date type."
        });
      }

      for (const warning of item.warnings) {
        warnings.push({
          level: "warning",
          blockId: block.block_id,
          column: item.column,
          message: `Parser warning: ${warning}.`
        });
      }
    }

    for (const item of block.date_issues || []) {
      warnings.push({
        level: "warning",
        blockId: block.block_id,
        column: item.column,
        message: `${item.issue}. Examples: ${item.example_values.join(", ")}`
      });
    }

    for (const item of block.missing_by_column || []) {
      if (item.ratio >= 0.4) {
        warnings.push({
          level: "warning",
          blockId: block.block_id,
          column: item.column,
          message: `High missingness: ${item.missing}/${item.total} values are empty.`
        });
      }
    }
  }

  return { errors, warnings };
}

function estimateCommitRows(preview: PreviewPayload | null): number {
  let total = 0;
  for (const block of preview?.blocks || []) {
    const measures = countByRole(block).measure;
    const estimatedDataRows = Math.max((block.row_count || 0) - 1, block.sample_rows.length);
    total += estimatedDataRows * measures;
  }
  return total;
}

export default function UploadWorkflowPage() {
  return (
    <Suspense
      fallback={
        <section className="surface-card flex min-h-[320px] items-center justify-center px-6 py-10">
          <p className="text-sm font-medium text-slate-500">Loading upload workflow...</p>
        </section>
      }
    >
      <UploadWorkflowPageContent />
    </Suspense>
  );
}

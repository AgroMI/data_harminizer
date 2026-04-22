"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { WorkflowStepper } from "../components/WorkflowStepper";
import { API_BASE, readProblemDetail, toErrorMessage } from "../lib/client";
import { pushRecentUpload, readRecentUploads, type RecentUploadItem } from "../lib/recent_uploads";
import { primaryWorkflowSteps } from "../lib/workflow";

type UploadResponse = {
  id: string;
};

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recentUploads, setRecentUploads] = useState<RecentUploadItem[]>([]);

  useEffect(() => {
    setRecentUploads(readRecentUploads());
  }, []);

  const selectedFileLabel = useMemo(() => {
    if (!file) {
      return "Choose an .xls or .xlsx workbook";
    }
    return `${file.name} · ${formatFileSize(file.size)}`;
  }, [file]);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();

    if (!file) {
      setError("Choose an Excel file first.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE}/uploads`, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Upload failed."));
      }

      const data = (await response.json()) as UploadResponse;
      setRecentUploads(pushRecentUpload({ id: data.id, filename: file.name }));
      router.push(`/uploads/${data.id}?stage=review`);
    } catch (caught) {
      setError(toErrorMessage(caught, "Upload failed."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <section className="surface-card px-6 py-8 sm:px-8 sm:py-10">
        <div className="grid gap-8 lg:grid-cols-[1.15fr,0.85fr]">
          <div className="space-y-5">
            <div className="space-y-3">
              <p className="eyebrow">Step 1</p>
              <h1 className="text-4xl font-semibold tracking-tight text-slate-950">Upload a workbook</h1>
              <p className="max-w-2xl text-base leading-7 text-slate-600">
                Start with a single Excel file. The system will parse the sheets, detect blocks and open a focused review workflow for mapping and validation.
              </p>
            </div>

            <WorkflowStepper steps={primaryWorkflowSteps()} activeKey="upload" />

            <Notice tone="info" title="Main path">
              {"Upload -> review -> mapping -> validation -> commit -> browse -> AI query."}
            </Notice>
          </div>

          <div className="surface-card-muted p-5">
            <p className="eyebrow">Before you upload</p>
            <ul className="mt-3 grid gap-2 text-sm leading-6 text-slate-600">
              <li>Accepted formats: `.xls`, `.xlsx`, `.xlsm`, `.xltx`, `.xltm`</li>
              <li>Use one workbook per run</li>
              <li>After upload you will land in the review step automatically</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.15fr,0.85fr]">
        <section className="surface-card px-6 py-8">
          <div className="space-y-3">
            <p className="eyebrow">Upload</p>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Drop a file and continue</h2>
            <p className="text-sm leading-6 text-slate-600">
              One primary action only: upload the workbook and move into the guided workflow.
            </p>
          </div>

          <form onSubmit={onSubmit} className="mt-8 space-y-5">
            <label
              htmlFor="file-upload"
              className="group flex cursor-pointer flex-col items-center justify-center rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50/80 px-6 py-12 text-center transition hover:border-cyan-300 hover:bg-cyan-50/70"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-xl shadow-panel">
                ↑
              </div>
              <p className="mt-5 text-base font-semibold text-slate-900">{selectedFileLabel}</p>
              <p className="mt-2 text-sm text-slate-500">Click to browse or replace the selected workbook.</p>
              <input
                id="file-upload"
                type="file"
                className="sr-only"
                accept=".xls,.xlsx,.xlsm,.xltx,.xltm"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
            </label>

            {error ? <Notice tone="error">{error}</Notice> : null}

            <div className="flex flex-wrap gap-3">
              <button type="submit" className="btn-primary px-6" disabled={loading}>
                {loading ? "Uploading..." : "Upload and open review"}
              </button>
              <button type="button" className="btn-ghost px-6" onClick={() => setFile(null)} disabled={!file || loading}>
                Clear
              </button>
            </div>
          </form>
        </section>

        <section className="surface-card-muted px-6 py-8">
          <div className="space-y-3">
            <p className="eyebrow">Recent uploads</p>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Pick up where you left off</h2>
          </div>

          <div className="mt-6">
            {recentUploads.length === 0 ? (
              <EmptyState
                title="No recent uploads"
                body="Once you upload a workbook, it will appear here as a quick shortcut back into the workflow."
              />
            ) : (
              <div className="grid gap-3">
                {recentUploads.map((item) => (
                  <Link
                    key={item.id}
                    href={`/uploads/${encodeURIComponent(item.id)}?stage=review`}
                    className="rounded-[1.25rem] border border-slate-200 bg-white px-4 py-4 transition hover:border-cyan-200"
                  >
                    <p className="font-semibold text-slate-900">{item.filename}</p>
                    <p className="mt-1 text-xs text-slate-500">{item.id}</p>
                    <p className="mt-2 text-sm text-slate-600">
                      Last opened {new Date(item.visitedAt).toLocaleString("hu-HU")}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>
      </section>
    </div>
  );
}

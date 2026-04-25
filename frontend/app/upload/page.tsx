"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { API_BASE, readProblemDetail, toErrorMessage } from "../lib/client";
import type { UploadListItem, UploadListResponse } from "../lib/api_types";

type UploadResponse = { id: string };

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "committed") {
    return <span className="badge bg-emerald-100 text-emerald-700">Committed</span>;
  }
  if (status === "failed") {
    return <span className="badge bg-rose-100 text-rose-700">Failed</span>;
  }
  return <span className="badge bg-amber-100 text-amber-700">Review pending</span>;
}

function UploadHistory() {
  const [uploads, setUploads] = useState<UploadListItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/uploads`)
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load");
        return r.json() as Promise<UploadListResponse>;
      })
      .then((data) => setUploads(data.uploads))
      .catch(() => setError("Could not load upload history."));
  }, []);

  if (error) {
    return <Notice tone="error">{error}</Notice>;
  }

  if (uploads === null) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    );
  }

  if (uploads.length === 0) {
    return (
      <EmptyState
        title="No uploads yet"
        body="Once you upload a workbook it will appear here."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100">
            <th className="py-2.5 pr-6 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">File</th>
            <th className="py-2.5 pr-6 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Status</th>
            <th className="py-2.5 pr-6 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Sheets</th>
            <th className="py-2.5 pr-6 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Size</th>
            <th className="py-2.5 pr-6 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Uploaded</th>
            <th className="py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-400" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {uploads.map((item) => (
            <tr key={item.id} className="group">
              <td className="py-3.5 pr-6 font-medium text-slate-900">{item.original_filename}</td>
              <td className="py-3.5 pr-6">
                <StatusBadge status={item.status} />
              </td>
              <td className="py-3.5 pr-6 text-slate-500">{item.sheet_count}</td>
              <td className="py-3.5 pr-6 text-slate-500">
                {item.file_size_bytes != null ? formatFileSize(item.file_size_bytes) : "—"}
              </td>
              <td className="py-3.5 pr-6 text-slate-500">
                {item.uploaded_at
                  ? new Date(item.uploaded_at).toLocaleString("hu-HU")
                  : "—"}
              </td>
              <td className="py-3.5 text-right">
                <Link
                  href={`/uploads/${encodeURIComponent(item.id)}?stage=review`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-cyan-200 hover:text-cyan-700"
                >
                  Open <span aria-hidden>→</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedFileLabel = useMemo(() => {
    if (!file) return null;
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
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await readProblemDetail(response, "Upload failed."));
      }

      const data = (await response.json()) as UploadResponse;
      router.push(`/uploads/${data.id}?stage=review`);
    } catch (caught) {
      setError(toErrorMessage(caught, "Upload failed."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <section className="surface-card px-6 py-8 sm:px-8 sm:py-10">
        <div className="mb-7 space-y-1.5">
          <p className="eyebrow">New upload</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Upload a workbook</h1>
          <p className="text-sm leading-6 text-slate-500">
            Accepted formats: .xls · .xlsx · .xlsm · .xltx · .xltm — one file per run. You&apos;ll land in the review step automatically.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <label
            htmlFor="file-upload"
            className="group flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/60 px-6 py-10 text-center transition hover:border-cyan-300 hover:bg-cyan-50/40"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white text-lg shadow-panel transition group-hover:shadow-float">
              ↑
            </div>
            <div className="space-y-1">
              {selectedFileLabel ? (
                <p className="font-semibold text-slate-900">{selectedFileLabel}</p>
              ) : (
                <p className="font-semibold text-slate-700">Drop a file here or click to browse</p>
              )}
              <p className="text-sm text-slate-400">
                {selectedFileLabel ? "Click to replace the selected file." : ".xls, .xlsx, .xlsm, .xltx, .xltm"}
              </p>
            </div>
            <input
              id="file-upload"
              type="file"
              className="sr-only"
              accept=".xls,.xlsx,.xlsm,.xltx,.xltm"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setError("");
              }}
            />
          </label>

          {error ? <Notice tone="error">{error}</Notice> : null}

          <div className="flex flex-wrap gap-3">
            <button type="submit" className="btn-primary px-7" disabled={loading || !file}>
              {loading ? "Uploading…" : "Upload and continue"}
            </button>
            {file ? (
              <button
                type="button"
                className="btn-ghost px-7"
                onClick={() => setFile(null)}
                disabled={loading}
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section className="surface-card px-6 py-8 sm:px-8 sm:py-10">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1.5">
            <p className="eyebrow">Előzmények</p>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Korábbi feltöltések</h2>
          </div>
          <Link href="/uploads" className="btn-ghost px-5 text-sm">
            Összes megtekintése →
          </Link>
        </div>
        <UploadHistory />
      </section>
    </div>
  );
}

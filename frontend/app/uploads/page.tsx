"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { API_BASE, toErrorMessage } from "../lib/client";
import type { UploadListItem, UploadListResponse } from "../lib/api_types";

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

function UploadCard({ item }: { item: UploadListItem }) {
  return (
    <div className="group rounded-2xl border border-slate-100 bg-white px-5 py-4 transition hover:border-cyan-200 hover:shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate font-semibold text-slate-900">{item.original_filename}</p>
            <StatusBadge status={item.status} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            {item.sheet_count > 0 && (
              <span>{item.sheet_count} {item.sheet_count === 1 ? "worksheet" : "worksheets"}</span>
            )}
            {item.file_size_bytes != null && (
              <span>{formatFileSize(item.file_size_bytes)}</span>
            )}
            {item.uploaded_at && (
              <span>{new Date(item.uploaded_at).toLocaleString("en-US")}</span>
            )}
            <span className="font-mono text-[11px] text-slate-400">{item.id}</span>
          </div>
        </div>

        <div className="flex shrink-0 gap-2">
          <Link
            href={`/uploads/${encodeURIComponent(item.id)}?stage=review`}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-cyan-200 hover:text-cyan-700"
          >
            Open →
          </Link>
          {item.status === "committed" && (
            <Link
              href={`/workspace?upload_session_id=${encodeURIComponent(item.id)}`}
              className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3.5 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100"
            >
              Data view
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

export default function UploadsListPage() {
  const [uploads, setUploads] = useState<UploadListItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/uploads`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<UploadListResponse>;
      })
      .then((data) => setUploads(data.uploads))
      .catch((err) => setError(toErrorMessage(err, "Failed to load uploads.")));
  }, []);

  const committed = uploads?.filter((u) => u.status === "committed") ?? [];
  const pending = uploads?.filter((u) => u.status !== "committed") ?? [];

  return (
    <div className="space-y-5">
      <section className="surface-card px-6 py-8 sm:px-8 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-1.5">
            <p className="eyebrow">Uploads</p>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Excel workbooks</h1>
            <p className="text-sm leading-6 text-slate-500">
              All uploaded files, with status and quick links.
            </p>
          </div>
          <Link href="/upload" className="btn-primary px-6">
            + New upload
          </Link>
        </div>
      </section>

      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : uploads === null ? (
        <section className="surface-card px-6 py-8 sm:px-8">
          <div className="space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
        </section>
      ) : uploads.length === 0 ? (
        <section className="surface-card px-6 py-8 sm:px-8">
          <EmptyState
            title="No uploads yet"
            body="Upload an Excel workbook and it will appear here."
            action={
              <Link href="/upload" className="btn-primary px-6">
                Start upload
              </Link>
            }
          />
        </section>
      ) : (
        <>
          {pending.length > 0 && (
            <section className="surface-card px-6 py-6 sm:px-8">
              <div className="mb-4 flex items-center gap-3">
                <p className="eyebrow">In progress</p>
                <span className="badge bg-amber-100 text-amber-700">{pending.length}</span>
              </div>
              <div className="space-y-2">
                {pending.map((item) => (
                  <UploadCard key={item.id} item={item} />
                ))}
              </div>
            </section>
          )}

          {committed.length > 0 && (
            <section className="surface-card px-6 py-6 sm:px-8">
              <div className="mb-4 flex items-center gap-3">
                <p className="eyebrow">Committed</p>
                <span className="badge bg-emerald-100 text-emerald-700">{committed.length}</span>
              </div>
              <div className="space-y-2">
                {committed.map((item) => (
                  <UploadCard key={item.id} item={item} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

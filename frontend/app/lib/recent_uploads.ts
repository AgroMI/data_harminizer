"use client";

export type RecentUploadItem = {
  id: string;
  filename: string;
  visitedAt: string;
};

const STORAGE_KEY = "atk_recent_uploads_v1";

export function readRecentUploads(): RecentUploadItem[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .filter((item): item is RecentUploadItem => {
        return Boolean(
          item &&
            typeof item === "object" &&
            typeof (item as RecentUploadItem).id === "string" &&
            typeof (item as RecentUploadItem).filename === "string" &&
            typeof (item as RecentUploadItem).visitedAt === "string"
        );
      })
      .slice(0, 8);
  } catch {
    return [];
  }
}

export function pushRecentUpload(item: { id: string; filename: string }): RecentUploadItem[] {
  if (typeof window === "undefined") {
    return [];
  }

  const nextItem: RecentUploadItem = {
    id: item.id,
    filename: item.filename,
    visitedAt: new Date().toISOString()
  };

  const nextItems = [
    nextItem,
    ...readRecentUploads().filter((existing) => existing.id !== item.id)
  ].slice(0, 8);

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextItems));
  return nextItems;
}

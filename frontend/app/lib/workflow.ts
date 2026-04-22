export type WorkflowStep = {
  key: string;
  label: string;
  href?: string;
};

export function uploadWorkflowSteps(uploadId?: string | null): WorkflowStep[] {
  const encoded = uploadId ? encodeURIComponent(uploadId) : "";
  const base = uploadId ? `/uploads/${encoded}` : "/upload";
  return [
    { key: "upload", label: "Upload", href: "/upload" },
    { key: "review", label: "Review", href: `${base}?stage=review` },
    { key: "mapping", label: "Mapping", href: `${base}?stage=mapping` },
    { key: "validation", label: "Validation", href: `${base}?stage=validation` },
    { key: "commit", label: "Commit", href: `${base}?stage=commit` },
    { key: "browse", label: "Browse", href: uploadId ? `/workspace?upload_session_id=${encoded}` : "/workspace" },
    { key: "ai", label: "AI Query", href: uploadId ? `/ai?upload_session_id=${encoded}` : "/ai" },
  ];
}

export function primaryWorkflowSteps(): WorkflowStep[] {
  return [
    { key: "upload", label: "Upload", href: "/upload" },
    { key: "review", label: "Review" },
    { key: "mapping", label: "Mapping" },
    { key: "validation", label: "Validation" },
    { key: "commit", label: "Commit" },
    { key: "browse", label: "Browse", href: "/workspace" },
    { key: "ai", label: "AI Query", href: "/ai" },
  ];
}

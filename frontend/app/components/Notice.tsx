import type { ReactNode } from "react";

import { cn } from "../lib/client";

type NoticeTone = "neutral" | "info" | "success" | "warning" | "error";

type NoticeProps = {
  tone?: NoticeTone;
  title?: string;
  children: ReactNode;
};

const TONE_CLASSES: Record<NoticeTone, string> = {
  neutral: "border-slate-200 bg-slate-50 text-slate-700",
  info: "border-cyan-200 bg-cyan-50 text-cyan-900",
  success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  error: "border-rose-200 bg-rose-50 text-rose-900",
};

export function Notice({ tone = "neutral", title, children }: NoticeProps) {
  return (
    <div className={cn("rounded-[1.2rem] border px-4 py-3 text-sm", TONE_CLASSES[tone])}>
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : ""}>{children}</div>
    </div>
  );
}

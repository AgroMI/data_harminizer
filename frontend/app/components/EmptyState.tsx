import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  body: string;
  action?: ReactNode;
};

export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-slate-200 bg-white/80 px-6 py-8 text-center">
      <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

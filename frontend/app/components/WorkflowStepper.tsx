import Link from "next/link";

import { cn } from "../lib/client";
import type { WorkflowStep } from "../lib/workflow";

type WorkflowStepperProps = {
  steps: WorkflowStep[];
  activeKey: string;
};

export function WorkflowStepper({ steps, activeKey }: WorkflowStepperProps) {
  const activeIndex = steps.findIndex((step) => step.key === activeKey);

  return (
    <nav aria-label="Workflow progress" className="overflow-x-auto">
      <ol className="flex min-w-max items-center gap-3">
        {steps.map((step, index) => {
          const isActive = step.key === activeKey;
          const isComplete = activeIndex >= 0 && index < activeIndex;

          const content = (
            <>
              <span
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold",
                  isActive
                    ? "bg-cyan-700 text-white"
                    : isComplete
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-slate-100 text-slate-500"
                )}
              >
                {index + 1}
              </span>
              <span className="text-sm font-medium text-slate-700">{step.label}</span>
            </>
          );

          return (
            <li key={step.key} className="flex items-center gap-3">
              {step.href ? (
                <Link
                  href={step.href}
                  className={cn(
                    "inline-flex items-center gap-3 rounded-full border px-3 py-2 transition",
                    isActive
                      ? "border-cyan-200 bg-cyan-50"
                      : "border-slate-200 bg-white hover:border-cyan-200"
                  )}
                >
                  {content}
                </Link>
              ) : (
                <div className="inline-flex items-center gap-3 rounded-full border border-slate-200 bg-white px-3 py-2">
                  {content}
                </div>
              )}

              {index < steps.length - 1 ? <span className="text-slate-300">/</span> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

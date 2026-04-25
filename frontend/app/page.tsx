import Link from "next/link";

import { WorkflowStepper } from "./components/WorkflowStepper";
import { primaryWorkflowSteps } from "./lib/workflow";

export default function HomePage() {
  return (
    <div className="space-y-5">
      <section className="surface-card px-8 py-12 sm:py-16">
        <div className="max-w-xl space-y-5">
          <div className="space-y-3">
            <p className="eyebrow">Agrarian Data Workflow</p>
            <h1 className="text-5xl font-semibold leading-[1.1] tracking-tight text-slate-950">
              From spreadsheet<br />to structured data.
            </h1>
            <p className="text-base leading-7 text-slate-600">
              Upload an Excel workbook, review and map the columns, commit to a harmonized agrarian dataset, then query it with natural language.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link href="/upload" className="btn-primary px-7">
              Start upload
            </Link>
            <Link href="/workspace" className="btn-ghost px-7">
              Browse data
            </Link>
            <Link href="/ai" className="btn-ghost px-7">
              AI query
            </Link>
          </div>
        </div>
      </section>

      <section className="surface-card px-6 py-6 sm:px-8">
        <p className="eyebrow mb-4">Workflow</p>
        <WorkflowStepper steps={primaryWorkflowSteps()} activeKey="upload" />
      </section>
    </div>
  );
}

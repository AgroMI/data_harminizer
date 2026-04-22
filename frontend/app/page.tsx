import Link from "next/link";

import { WorkflowStepper } from "./components/WorkflowStepper";
import { primaryWorkflowSteps } from "./lib/workflow";

const featureCards = [
  {
    title: "Workflow first",
    body: "The main interface follows a clear path from upload to committed data and AI-assisted querying."
  },
  {
    title: "Advanced details on demand",
    body: "Technical outputs such as SQL, audit trace and MCP tool payloads stay secondary instead of flooding the primary UI."
  },
  {
    title: "Production-leaning structure",
    body: "Loading, empty and error states are explicit, primary actions are obvious, and the main routes are intentionally small."
  }
];

export default function HomePage() {
  return (
    <div className="grid gap-6">
      <section className="surface-card px-6 py-8 sm:px-8 sm:py-10">
        <div className="space-y-6">
          <div className="space-y-3">
            <p className="eyebrow">Agrarian Data Workflow</p>
            <h1 className="max-w-4xl text-balance text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl">
              Upload, validate, commit, browse, ask.
            </h1>
            <p className="max-w-3xl text-base leading-7 text-slate-600 sm:text-lg">
              The frontend is now organized around the actual user workflow instead of the internal demo surfaces.
              Use the clean path for normal work, and open the AI screen only when you want natural language querying or advanced technical details.
            </p>
          </div>

          <WorkflowStepper steps={primaryWorkflowSteps()} activeKey="upload" />

          <div className="flex flex-wrap gap-3">
            <Link href="/upload" className="btn-primary px-6">
              Start upload
            </Link>
            <Link href="/workspace" className="btn-ghost px-6">
              Browse harmonized data
            </Link>
            <Link href="/ai" className="btn-ghost px-6">
              Open AI query
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        {featureCards.map((card) => (
          <article key={card.title} className="surface-card px-6 py-6">
            <p className="eyebrow">Why this matters</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{card.title}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">{card.body}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

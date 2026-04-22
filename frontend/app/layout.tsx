import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Semantic Harmonization Workbench",
  description: "Workflow-oriented Excel harmonization, browsing and AI query interface"
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <div className="relative mx-auto min-h-screen max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
          <div className="pointer-events-none absolute inset-x-10 top-0 -z-10 h-72 rounded-full bg-cyan-200/20 blur-3xl" />
          <div className="pointer-events-none absolute right-8 top-24 -z-10 h-64 w-64 rounded-full bg-coral-200/20 blur-3xl" />

          <div className="app-shell">
            <header className="border-b border-white/70 px-5 py-4 sm:px-7">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="eyebrow">Thesis Demo</p>
                  <Link href="/" className="text-lg font-semibold tracking-tight text-slate-900">
                    Semantic Harmonization Workbench
                  </Link>
                </div>

                <nav className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                  <Link href="/" className="btn-ghost min-h-10 px-4">
                    Home
                  </Link>
                  <Link href="/upload" className="btn-ghost min-h-10 px-4">
                    Upload
                  </Link>
                  <Link href="/workspace" className="btn-ghost min-h-10 px-4">
                    Workspace
                  </Link>
                  <Link href="/ai" className="btn-primary min-h-10 px-4">
                    AI Query
                  </Link>
                </nav>
              </div>
            </header>

            <main className="px-4 py-5 sm:px-7 sm:py-7">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { NavLink } from "./components/NavLink";
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
            <header className="border-b border-slate-100/80 px-5 py-3 sm:px-7">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="eyebrow text-[10px] leading-none">Thesis Demo</p>
                  <Link href="/" className="text-[15px] font-semibold tracking-tight text-slate-900 hover:text-cyan-700">
                    Semantic Harmonization Workbench
                  </Link>
                </div>

                <nav className="flex shrink-0 items-center gap-0.5">
                  <NavLink href="/">Home</NavLink>
                  <NavLink href="/upload">Upload</NavLink>
                  <NavLink href="/uploads">Files</NavLink>
                  <NavLink href="/workspace">Workspace</NavLink>
                  <NavLink href="/ai">AI Query</NavLink>
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

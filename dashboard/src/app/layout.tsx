import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PaperTrail — SEC Filing Contradiction Detector",
  description:
    "Real-time knowledge graph and contradiction detection for public company filings",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">
        <nav className="glass sticky top-0 z-50 border-b border-white/5">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <a href="/" className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold">
                PT
              </div>
              <span className="text-lg font-semibold tracking-tight">
                PaperTrail
              </span>
            </a>
            <div className="flex items-center gap-6 text-sm text-[var(--text-secondary)]">
              <a href="/" className="hover:text-white transition-colors">
                Dashboard
              </a>
              <a href="/#search" className="hover:text-white transition-colors">
                Search
              </a>
              <span className="rounded-full bg-brand-600/20 px-3 py-1 text-xs text-brand-400 border border-brand-600/30">
                MVP
              </span>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}

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
    <html lang="en">
      <body className="min-h-screen antialiased">
        <nav className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg-primary)]/90 backdrop-blur-md">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
            <a href="/" className="flex items-center gap-2.5">
              <span className="font-serif text-xl font-semibold tracking-tight text-warm-950">
                PaperTrail
              </span>
            </a>
            <div className="flex items-center gap-6 text-[13px] text-[var(--text-secondary)]">
              <a href="/" className="hover:text-warm-950 transition-colors">
                Dashboard
              </a>
              <a href="/#search" className="hover:text-warm-950 transition-colors">
                Search
              </a>
              <span className="rounded-full border border-[var(--border)] px-2.5 py-0.5 text-[11px] tracking-wide text-[var(--text-muted)]">
                MVP
              </span>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-5 py-10">{children}</main>
      </body>
    </html>
  );
}

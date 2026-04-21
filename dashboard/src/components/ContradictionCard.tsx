"use client";

import type { Contradiction } from "@/lib/api";
import SeverityBadge from "./SeverityBadge";

export default function ContradictionCard({
  contradiction: c,
}: {
  contradiction: Contradiction;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 transition-colors hover:border-[var(--border-hover)]">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[13px] font-semibold text-warm-950">
            {c.company_ticker}
          </span>
          <span className="text-[13px] text-[var(--text-muted)]">
            {c.company_name}
          </span>
        </div>
        <SeverityBadge severity={c.severity} />
      </div>

      {/* Claim A */}
      <div className="mb-3 rounded-xl bg-[var(--bg-primary)] p-3.5">
        <div className="mb-1.5 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent-400" />
          <span className="uppercase tracking-wide font-medium">Original</span>
          {c.claim_a.claim_date && (
            <span className="ml-auto">{c.claim_a.claim_date}</span>
          )}
        </div>
        <p className="text-[13px] leading-relaxed text-warm-800">{c.claim_a.claim_text}</p>
        <div className="mt-2 flex gap-1.5">
          {c.claim_a.topic && (
            <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              {c.claim_a.topic}
            </span>
          )}
          {c.claim_a.sentiment && (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] ${
                c.claim_a.sentiment === "positive"
                  ? "border-emerald-800/50 bg-emerald-950/50 text-emerald-300"
                  : c.claim_a.sentiment === "negative"
                    ? "border-red-800/50 bg-red-950/50 text-red-300"
                    : "border-[var(--border)] text-[var(--text-muted)]"
              }`}
            >
              {c.claim_a.sentiment}
            </span>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="my-3 flex items-center">
        <div className="h-px flex-1 bg-[var(--border)]" />
        <span className="mx-3 text-[10px] font-semibold uppercase tracking-[0.1em] text-severity-critical">
          contradicts
        </span>
        <div className="h-px flex-1 bg-[var(--border)]" />
      </div>

      {/* Claim B */}
      <div className="mb-3 rounded-xl border border-red-900/40 bg-red-950/35 p-3.5">
        <div className="mb-1.5 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-severity-critical" />
          <span className="uppercase tracking-wide font-medium">Contradiction</span>
          {c.claim_b.claim_date && (
            <span className="ml-auto">{c.claim_b.claim_date}</span>
          )}
        </div>
        <p className="text-[13px] leading-relaxed text-warm-800">{c.claim_b.claim_text}</p>
        <div className="mt-2 flex gap-1.5">
          {c.claim_b.topic && (
            <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
              {c.claim_b.topic}
            </span>
          )}
        </div>
      </div>

      {/* AI Analysis */}
      {c.agent_reasoning && (
        <div className="mb-3 rounded-xl border border-accent-400/30 bg-accent-50 p-3.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent-400">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
            </svg>
            Analysis
          </div>
          <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {c.agent_reasoning}
          </p>
        </div>
      )}

      {/* Scores */}
      <div className="mt-4 flex items-center gap-4 text-[11px] text-[var(--text-muted)]">
        <div className="flex items-center gap-1">
          <span>Similarity</span>
          <span className="font-mono font-medium text-warm-800">
            {(c.similarity_score * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span>NLI</span>
          <span className="font-mono font-medium text-warm-800">
            {(c.nli_contradiction_score * 100).toFixed(0)}%
          </span>
        </div>
        {c.time_gap_days != null && (
          <div className="flex items-center gap-1">
            <span>Gap</span>
            <span className="font-mono font-medium text-warm-800">
              {c.time_gap_days}d
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

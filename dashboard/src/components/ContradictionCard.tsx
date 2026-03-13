"use client";

import type { Contradiction } from "@/lib/api";
import SeverityBadge from "./SeverityBadge";

export default function ContradictionCard({
  contradiction: c,
}: {
  contradiction: Contradiction;
}) {
  return (
    <div className="glass rounded-xl p-5 transition-all hover:border-white/10">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <span className="text-sm font-semibold text-brand-400">
            {c.company_ticker}
          </span>
          <span className="mx-2 text-[var(--text-secondary)]">&middot;</span>
          <span className="text-sm text-[var(--text-secondary)]">
            {c.company_name}
          </span>
        </div>
        <SeverityBadge severity={c.severity} />
      </div>

      {/* Claim A - Original Statement */}
      <div className="mb-3 rounded-lg bg-white/[0.03] p-3.5">
        <div className="mb-1.5 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400" />
          Original Claim
          {c.claim_a.claim_date && (
            <span className="ml-auto">{c.claim_a.claim_date}</span>
          )}
        </div>
        <p className="text-sm leading-relaxed">{c.claim_a.claim_text}</p>
        <div className="mt-2 flex gap-2">
          {c.claim_a.topic && (
            <span className="rounded bg-white/5 px-2 py-0.5 text-xs text-[var(--text-secondary)]">
              {c.claim_a.topic}
            </span>
          )}
          {c.claim_a.sentiment && (
            <span
              className={`rounded px-2 py-0.5 text-xs ${
                c.claim_a.sentiment === "positive"
                  ? "bg-green-500/10 text-green-400"
                  : c.claim_a.sentiment === "negative"
                    ? "bg-red-500/10 text-red-400"
                    : "bg-gray-500/10 text-gray-400"
              }`}
            >
              {c.claim_a.sentiment}
            </span>
          )}
        </div>
      </div>

      {/* Arrow / Contradiction indicator */}
      <div className="my-2 flex items-center justify-center">
        <div className="h-px flex-1 bg-red-500/20" />
        <span className="mx-3 text-xs font-medium text-red-400">
          CONTRADICTS
        </span>
        <div className="h-px flex-1 bg-red-500/20" />
      </div>

      {/* Claim B - Contradicting Statement */}
      <div className="mb-3 rounded-lg bg-red-500/[0.04] border border-red-500/10 p-3.5">
        <div className="mb-1.5 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400" />
          Contradicting Claim
          {c.claim_b.claim_date && (
            <span className="ml-auto">{c.claim_b.claim_date}</span>
          )}
        </div>
        <p className="text-sm leading-relaxed">{c.claim_b.claim_text}</p>
        <div className="mt-2 flex gap-2">
          {c.claim_b.topic && (
            <span className="rounded bg-white/5 px-2 py-0.5 text-xs text-[var(--text-secondary)]">
              {c.claim_b.topic}
            </span>
          )}
        </div>
      </div>

      {/* Scores */}
      <div className="mt-4 flex items-center gap-4 text-xs text-[var(--text-secondary)]">
        <div className="flex items-center gap-1.5">
          <span>Similarity:</span>
          <span className="font-mono text-white">
            {(c.similarity_score * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span>NLI Score:</span>
          <span className="font-mono text-white">
            {(c.nli_contradiction_score * 100).toFixed(0)}%
          </span>
        </div>
        {c.time_gap_days != null && (
          <div className="flex items-center gap-1.5">
            <span>Time Gap:</span>
            <span className="font-mono text-white">
              {c.time_gap_days} days
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

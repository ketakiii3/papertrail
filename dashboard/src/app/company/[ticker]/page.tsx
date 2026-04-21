"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ContradictionCard from "@/components/ContradictionCard";
import Timeline from "@/components/Timeline";
import type {
  Company,
  Contradiction,
  Timeline as TimelineType,
  Claim,
} from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "";

export default function CompanyPage() {
  const params = useParams();
  const ticker = (params.ticker as string).toUpperCase();

  const [company, setCompany] = useState<Company | null>(null);
  const [timeline, setTimeline] = useState<TimelineType | null>(null);
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [tab, setTab] = useState<"timeline" | "contradictions" | "claims">(
    "timeline"
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/companies/${ticker}`)
      .then((r) => {
        if (!r.ok) throw new Error("Company not found");
        return r.json();
      })
      .then(setCompany)
      .catch((e) => setError(e.message));

    fetch(`${API}/api/v1/companies/${ticker}/timeline`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setTimeline)
      .catch(() => {});

    fetch(`${API}/api/v1/companies/${ticker}/contradictions`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setContradictions)
      .catch(() => {});

    fetch(`${API}/api/v1/companies/${ticker}/claims?limit=100`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setClaims)
      .catch(() => {});
  }, [ticker]);

  if (error) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-14 text-center">
        <p className="text-severity-critical text-[14px]">{error}</p>
        <a href="/" className="mt-4 inline-block text-[13px] text-accent-500 underline underline-offset-2 decoration-accent-200 hover:decoration-accent-400">
          Back to Dashboard
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Company Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-secondary)] font-serif text-xl text-warm-600">
          {ticker.slice(0, 2)}
        </div>
        <div>
          <h1 className="font-serif text-2xl font-normal text-warm-950">
            {company?.name || ticker}
          </h1>
          <div className="flex items-center gap-2.5 text-[13px] text-[var(--text-secondary)]">
            <span className="font-mono text-[12px] font-medium">{ticker}</span>
            {company?.sector && (
              <>
                <span className="text-[var(--text-muted)]">&middot;</span>
                <span>{company.sector}</span>
              </>
            )}
            <span className="text-[var(--text-muted)]">&middot;</span>
            <span>{contradictions.length} contradictions</span>
            <span className="text-[var(--text-muted)]">&middot;</span>
            <span>{claims.length} claims</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {(["timeline", "contradictions", "claims"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1.5 text-[13px] font-medium capitalize transition-colors ${
              tab === t
                ? "bg-warm-800 text-warm-50"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-warm-200 hover:text-warm-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "timeline" && (
        <Timeline events={timeline?.events || []} />
      )}

      {tab === "contradictions" && (
        <div className="space-y-5">
          {contradictions.length === 0 ? (
            <p className="text-center text-[14px] text-[var(--text-secondary)] py-14">
              No contradictions found for {ticker}
            </p>
          ) : (
            contradictions.map((c) => (
              <ContradictionCard key={c.id} contradiction={c} />
            ))
          )}
        </div>
      )}

      {tab === "claims" && (
        <div className="space-y-2">
          {claims.length === 0 ? (
            <p className="text-center text-[14px] text-[var(--text-secondary)] py-14">
              No claims extracted for {ticker}
            </p>
          ) : (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Claim</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Topic</th>
                    <th className="px-4 py-3">Sentiment</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.map((claim) => (
                    <tr
                      key={claim.id}
                      className="border-b border-[var(--border)]/50 transition-colors hover:bg-[var(--bg-secondary)]"
                    >
                      <td className="px-4 py-3 text-[12px] text-[var(--text-muted)] whitespace-nowrap">
                        {claim.claim_date || "\u2014"}
                      </td>
                      <td className="px-4 py-3 max-w-md">
                        <p className="line-clamp-2 text-warm-700 leading-relaxed">{claim.claim_text}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                          {claim.claim_type || "\u2014"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] text-[var(--text-muted)]">
                          {claim.topic || "\u2014"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[10px] ${
                            claim.sentiment === "positive"
                              ? "border-emerald-800/50 bg-emerald-950/50 text-emerald-300"
                              : claim.sentiment === "negative"
                                ? "border-red-800/50 bg-red-950/50 text-red-300"
                                : "border-[var(--border)] text-[var(--text-muted)]"
                          }`}
                        >
                          {claim.sentiment || "\u2014"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

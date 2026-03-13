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
      <div className="glass rounded-xl p-12 text-center">
        <p className="text-red-400">{error}</p>
        <a href="/" className="mt-4 inline-block text-brand-400 hover:underline">
          Back to Dashboard
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Company Header */}
      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-brand-600/20 text-xl font-bold text-brand-400">
          {ticker.slice(0, 2)}
        </div>
        <div>
          <h1 className="text-2xl font-bold">
            {company?.name || ticker}
          </h1>
          <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
            <span className="font-mono">{ticker}</span>
            {company?.sector && (
              <>
                <span>&middot;</span>
                <span>{company.sector}</span>
              </>
            )}
            <span>&middot;</span>
            <span>{contradictions.length} contradictions</span>
            <span>&middot;</span>
            <span>{claims.length} claims</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-white/[0.04] p-1">
        {(["timeline", "contradictions", "claims"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium capitalize transition-colors ${
              tab === t
                ? "bg-white/10 text-white"
                : "text-[var(--text-secondary)] hover:text-white"
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
        <div className="space-y-4">
          {contradictions.length === 0 ? (
            <p className="text-center text-sm text-[var(--text-secondary)] py-12">
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
            <p className="text-center text-sm text-[var(--text-secondary)] py-12">
              No claims extracted for {ticker}
            </p>
          ) : (
            <div className="glass rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5 text-left text-xs text-[var(--text-secondary)]">
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
                      className="border-b border-white/[0.03] hover:bg-white/[0.02]"
                    >
                      <td className="px-4 py-3 text-xs text-[var(--text-secondary)] whitespace-nowrap">
                        {claim.claim_date || "—"}
                      </td>
                      <td className="px-4 py-3 max-w-md">
                        <p className="line-clamp-2">{claim.claim_text}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-white/5 px-2 py-0.5 text-xs">
                          {claim.claim_type || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-white/5 px-2 py-0.5 text-xs">
                          {claim.topic || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded px-2 py-0.5 text-xs ${
                            claim.sentiment === "positive"
                              ? "bg-green-500/10 text-green-400"
                              : claim.sentiment === "negative"
                                ? "bg-red-500/10 text-red-400"
                                : "bg-gray-500/10 text-gray-400"
                          }`}
                        >
                          {claim.sentiment || "—"}
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

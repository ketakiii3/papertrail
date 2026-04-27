"use client";

import { useEffect, useState } from "react";
import SearchBar from "@/components/SearchBar";
import StatsCards from "@/components/StatsCards";
import ContradictionCard from "@/components/ContradictionCard";
import SeverityChart from "@/components/SeverityChart";
import LiveFeed from "@/components/LiveFeed";
import SurveillancePanel from "@/components/SurveillancePanel";
import type { Stats, Contradiction } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "";

export default function Home() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/v1/stats`).then((r) => r.ok ? r.json() : null).then(setStats).catch(() => {});
    fetch(`${API}/api/v1/contradictions/latest?limit=20`)
      .then((r) => r.ok ? r.json() : []).then(setContradictions).catch(() => {});
  }, []);

  const filtered = filter
    ? contradictions.filter((c) => c.severity === filter)
    : contradictions;

  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="pt-8 pb-2">
        <h1 className="font-serif text-[clamp(2.25rem,5vw,3.5rem)] font-light italic leading-[1.1] tracking-tight text-warm-950 text-center mb-4">
          SEC Filing Contradictions
        </h1>
        <p className="text-[15px] text-[var(--text-secondary)] max-w-xl mx-auto text-center leading-relaxed mb-10">
          Tracking what public companies say versus what they do.
          NLP-powered claim extraction and semantic contradiction detection.
        </p>
        <div className="flex justify-center">
          <SearchBar />
        </div>
      </section>

      {/* Stats */}
      <StatsCards stats={stats} />

      {/* Charts + Live Feed */}
      <div className="grid gap-5 md:grid-cols-2">
        <SeverityChart stats={stats} />
        <LiveFeed />
      </div>

      {/* Surveillance */}
      <SurveillancePanel />

      {/* Contradictions Feed */}
      <section>
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-serif text-2xl font-normal text-warm-950">
            Latest Contradictions
          </h2>
          <div className="flex gap-2">
            {["critical", "high", "medium", "low"].map((sev) => (
              <button
                key={sev}
                onClick={() => setFilter(filter === sev ? null : sev)}
                className={`rounded-full border px-3 py-1 text-[12px] font-medium capitalize transition-colors ${
                  filter === sev
                    ? "border-accent-500 bg-accent-50 text-accent-500"
                    : "border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-warm-700"
                }`}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-14 text-center">
            <p className="text-[var(--text-secondary)] text-[14px]">
              No contradictions found matching this filter.
            </p>
          </div>
        ) : (
          <div className="grid gap-5 md:grid-cols-2">
            {filtered.map((c) => (
              <ContradictionCard key={c.id} contradiction={c} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

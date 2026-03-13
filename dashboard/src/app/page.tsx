"use client";

import { useEffect, useState } from "react";
import SearchBar from "@/components/SearchBar";
import StatsCards from "@/components/StatsCards";
import ContradictionCard from "@/components/ContradictionCard";
import SeverityChart from "@/components/SeverityChart";
import LiveFeed from "@/components/LiveFeed";
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
    <div className="space-y-8">
      {/* Hero */}
      <section className="text-center py-8">
        <h1 className="text-4xl font-bold tracking-tight mb-3">
          SEC Filing{" "}
          <span className="bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent">
            Contradiction Detector
          </span>
        </h1>
        <p className="text-[var(--text-secondary)] max-w-2xl mx-auto mb-8">
          Real-time knowledge graph tracking what public companies say vs. what
          they do. Powered by NLP claim extraction and semantic contradiction
          detection.
        </p>
        <div className="flex justify-center">
          <SearchBar />
        </div>
      </section>

      {/* Stats */}
      <StatsCards stats={stats} />

      {/* Charts + Live Feed */}
      <div className="grid gap-4 md:grid-cols-2">
        <SeverityChart stats={stats} />
        <LiveFeed />
      </div>

      {/* Contradictions Feed */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Latest Contradictions</h2>
          <div className="flex gap-2">
            {["critical", "high", "medium", "low"].map((sev) => (
              <button
                key={sev}
                onClick={() => setFilter(filter === sev ? null : sev)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                  filter === sev
                    ? "border-brand-500/50 bg-brand-500/10 text-brand-400"
                    : "border-white/10 text-[var(--text-secondary)] hover:border-white/20"
                }`}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="glass rounded-xl p-12 text-center">
            <p className="text-[var(--text-secondary)]">
              No contradictions found matching this filter.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filtered.map((c) => (
              <ContradictionCard key={c.id} contradiction={c} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

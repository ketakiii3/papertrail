"use client";

import type { Stats } from "@/lib/api";

export default function StatsCards({ stats }: { stats: Stats | null }) {
  const cards = [
    { label: "Companies Tracked", value: stats?.total_companies ?? "\u2014" },
    { label: "Filings Processed", value: stats?.total_filings ?? "\u2014" },
    { label: "Claims Extracted", value: stats?.total_claims ?? "\u2014" },
    { label: "Contradictions Found", value: stats?.total_contradictions ?? "\u2014" },
  ];

  return (
    <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5"
        >
          <p className="text-[12px] font-medium tracking-wide text-[var(--text-muted)] uppercase">
            {card.label}
          </p>
          <p className="mt-2 font-serif text-3xl font-light text-warm-950">
            {typeof card.value === "number"
              ? card.value.toLocaleString()
              : card.value}
          </p>
        </div>
      ))}
    </div>
  );
}

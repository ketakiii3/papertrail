"use client";

import type { Stats } from "@/lib/api";

export default function StatsCards({ stats }: { stats: Stats | null }) {
  const cards = [
    {
      label: "Companies Tracked",
      value: stats?.total_companies ?? "—",
      color: "text-brand-400",
    },
    {
      label: "Filings Processed",
      value: stats?.total_filings ?? "—",
      color: "text-purple-400",
    },
    {
      label: "Claims Extracted",
      value: stats?.total_claims ?? "—",
      color: "text-cyan-400",
    },
    {
      label: "Contradictions Found",
      value: stats?.total_contradictions ?? "—",
      color: "text-red-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="glass rounded-xl p-4">
          <p className="text-xs text-[var(--text-secondary)]">{card.label}</p>
          <p className={`mt-1 text-2xl font-bold ${card.color}`}>
            {typeof card.value === "number"
              ? card.value.toLocaleString()
              : card.value}
          </p>
        </div>
      ))}
    </div>
  );
}

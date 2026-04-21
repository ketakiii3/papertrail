"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { Stats } from "@/lib/api";

const COLORS: Record<string, string> = {
  critical: "#C2423E",
  high: "#C27830",
  medium: "#A89032",
  low: "#4A8B5C",
};

export default function SeverityChart({ stats }: { stats: Stats | null }) {
  if (!stats || !stats.contradictions_by_severity) return null;

  const data = ["critical", "high", "medium", "low"].map((sev) => ({
    name: sev,
    count: stats.contradictions_by_severity[sev] || 0,
  }));

  if (data.every((d) => d.count === 0)) return null;

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6">
      <h3 className="font-sans text-[12px] font-medium uppercase tracking-wide text-[var(--text-muted)] mb-5">
        Contradictions by Severity
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <XAxis
            dataKey="name"
            tick={{ fill: "#8c7e6a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#8c7e6a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#161311",
              border: "1px solid #2a2620",
              borderRadius: "10px",
              color: "#e8e4dc",
              fontSize: "13px",
              fontFamily: "Plus Jakarta Sans",
            }}
          />
          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={COLORS[entry.name] || "#6b6154"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

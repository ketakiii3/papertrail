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
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

export default function SeverityChart({ stats }: { stats: Stats | null }) {
  if (!stats || !stats.contradictions_by_severity) return null;

  const data = ["critical", "high", "medium", "low"].map((sev) => ({
    name: sev,
    count: stats.contradictions_by_severity[sev] || 0,
  }));

  if (data.every((d) => d.count === 0)) return null;

  return (
    <div className="glass rounded-xl p-5">
      <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-4">
        Contradictions by Severity
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <XAxis
            dataKey="name"
            tick={{ fill: "#a0a0b0", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#a0a0b0", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1a1a2e",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "8px",
              color: "#f0f0f5",
            }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={COLORS[entry.name] || "#666"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

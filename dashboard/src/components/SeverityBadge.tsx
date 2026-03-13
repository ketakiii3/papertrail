"use client";

const SEVERITY_STYLES = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30 glow-red",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30 glow-orange",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30 glow-yellow",
  low: "bg-green-500/15 text-green-400 border-green-500/30 glow-green",
} as const;

export default function SeverityBadge({
  severity,
}: {
  severity: string;
}) {
  const style =
    SEVERITY_STYLES[severity as keyof typeof SEVERITY_STYLES] ||
    SEVERITY_STYLES.low;

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider ${style}`}
    >
      {severity}
    </span>
  );
}

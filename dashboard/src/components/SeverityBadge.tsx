"use client";

const SEVERITY_STYLES = {
  critical:
    "bg-red-950/50 text-red-300 border-red-800/40",
  high: "bg-orange-950/50 text-orange-300 border-orange-800/40",
  medium: "bg-yellow-950/50 text-yellow-200 border-yellow-800/40",
  low: "bg-emerald-950/50 text-emerald-300 border-emerald-800/40",
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
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] ${style}`}
    >
      {severity}
    </span>
  );
}

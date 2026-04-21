"use client";

import type { TimelineEvent } from "@/lib/api";
import SeverityBadge from "./SeverityBadge";

export default function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return (
      <p className="text-center text-[14px] text-[var(--text-secondary)] py-14">
        No timeline events yet. Run the ingester to process filings.
      </p>
    );
  }

  return (
    <div className="relative">
      <div className="absolute left-[19px] top-0 h-full w-px bg-[var(--border)]" />

      <div className="space-y-4">
        {events.map((event, i) => (
          <div key={i} className="relative flex gap-4 pl-2">
            <div
              className={`relative z-10 mt-2 h-3 w-3 shrink-0 rounded-full border-2 ${
                event.type === "contradiction"
                  ? "border-severity-critical bg-red-950"
                  : "border-accent-400 bg-accent-50"
              }`}
            />

            <div className="flex-1 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[12px] text-[var(--text-muted)]">
                  {event.date}
                </span>
                {event.type === "filing" ? (
                  <span className="rounded-full border border-[var(--border)] bg-[var(--bg-secondary)] px-2.5 py-0.5 text-[10px] font-semibold tracking-wide text-warm-600">
                    {event.data.form_type}
                  </span>
                ) : (
                  <SeverityBadge severity={event.data.severity} />
                )}
              </div>

              {event.type === "filing" ? (
                <p className="text-[13px] text-warm-800">
                  {event.data.form_type} Filing
                  {event.data.claim_count > 0 && (
                    <span className="text-[var(--text-muted)]">
                      {" \u00B7 "}{event.data.claim_count} claims extracted
                    </span>
                  )}
                </p>
              ) : (
                <div>
                  <p className="text-[13px] font-medium text-severity-critical mb-2">
                    Contradiction Detected
                  </p>
                  <div className="space-y-2 text-[12px]">
                    <div className="rounded-lg bg-[var(--bg-primary)] p-2.5">
                      <span className="text-[var(--text-muted)] text-[11px]">
                        Original ({event.data.claim_a_date})
                      </span>
                      <p className="mt-0.5 text-warm-800 leading-relaxed">
                        &ldquo;{event.data.claim_a_text}&rdquo;
                      </p>
                    </div>
                    <div className="rounded-lg border border-red-900/40 bg-red-950/35 p-2.5">
                      <span className="text-[var(--text-muted)] text-[11px]">
                        Contradiction ({event.data.claim_b_date})
                      </span>
                      <p className="mt-0.5 text-warm-800 leading-relaxed">
                        &ldquo;{event.data.claim_b_text}&rdquo;
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

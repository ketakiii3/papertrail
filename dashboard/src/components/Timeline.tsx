"use client";

import type { TimelineEvent } from "@/lib/api";
import SeverityBadge from "./SeverityBadge";

export default function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return (
      <p className="text-center text-sm text-[var(--text-secondary)] py-12">
        No timeline events yet. Run the ingester to process filings.
      </p>
    );
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-[19px] top-0 h-full w-px bg-white/10" />

      <div className="space-y-4">
        {events.map((event, i) => (
          <div key={i} className="relative flex gap-4 pl-2">
            {/* Dot */}
            <div
              className={`relative z-10 mt-1.5 h-3 w-3 shrink-0 rounded-full border-2 ${
                event.type === "contradiction"
                  ? "border-red-400 bg-red-500/30"
                  : "border-brand-400 bg-brand-500/30"
              }`}
            />

            {/* Content */}
            <div className="glass flex-1 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-[var(--text-secondary)]">
                  {event.date}
                </span>
                {event.type === "filing" ? (
                  <span className="rounded bg-brand-600/20 px-2 py-0.5 text-xs font-medium text-brand-400">
                    {event.data.form_type}
                  </span>
                ) : (
                  <SeverityBadge severity={event.data.severity} />
                )}
              </div>

              {event.type === "filing" ? (
                <div>
                  <p className="text-sm">
                    {event.data.form_type} Filing
                    {event.data.claim_count > 0 && (
                      <span className="text-[var(--text-secondary)]">
                        {" "}
                        &middot; {event.data.claim_count} claims extracted
                      </span>
                    )}
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-red-300 mb-2">
                    Contradiction Detected
                  </p>
                  <div className="space-y-2 text-xs">
                    <div className="rounded bg-white/[0.03] p-2">
                      <span className="text-[var(--text-secondary)]">
                        Original ({event.data.claim_a_date}):
                      </span>
                      <p className="mt-0.5">
                        &ldquo;{event.data.claim_a_text}&rdquo;
                      </p>
                    </div>
                    <div className="rounded bg-red-500/[0.05] border border-red-500/10 p-2">
                      <span className="text-[var(--text-secondary)]">
                        Contradiction ({event.data.claim_b_date}):
                      </span>
                      <p className="mt-0.5">
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

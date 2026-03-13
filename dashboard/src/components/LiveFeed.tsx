"use client";

import { useEffect, useState } from "react";
import SeverityBadge from "./SeverityBadge";

interface FeedEvent {
  type: string;
  data: {
    contradiction_id: number;
    company_ticker: string;
    severity: string;
  };
  timestamp: number;
}

// Simulated live feed for demo
const DEMO_EVENTS: Omit<FeedEvent, "timestamp">[] = [
  { type: "contradiction", data: { contradiction_id: 8, company_ticker: "JPM", severity: "critical" } },
  { type: "contradiction", data: { contradiction_id: 4, company_ticker: "MSFT", severity: "critical" } },
  { type: "contradiction", data: { contradiction_id: 2, company_ticker: "AAPL", severity: "critical" } },
  { type: "contradiction", data: { contradiction_id: 10, company_ticker: "AMZN", severity: "high" } },
  { type: "contradiction", data: { contradiction_id: 1, company_ticker: "AAPL", severity: "high" } },
  { type: "contradiction", data: { contradiction_id: 3, company_ticker: "MSFT", severity: "high" } },
  { type: "contradiction", data: { contradiction_id: 5, company_ticker: "TSLA", severity: "high" } },
  { type: "contradiction", data: { contradiction_id: 7, company_ticker: "META", severity: "high" } },
  { type: "contradiction", data: { contradiction_id: 9, company_ticker: "NVDA", severity: "medium" } },
  { type: "contradiction", data: { contradiction_id: 6, company_ticker: "TSLA", severity: "medium" } },
];

export default function LiveFeed() {
  const [events, setEvents] = useState<FeedEvent[]>([]);

  useEffect(() => {
    // Populate initial events with staggered timestamps
    const now = Date.now();
    const initial = DEMO_EVENTS.map((e, i) => ({
      ...e,
      timestamp: now - i * 180000, // 3 min apart
    }));
    setEvents(initial);
  }, []);

  return (
    <div className="glass rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-[var(--text-secondary)]">
          Live Feed
        </h3>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-xs text-[var(--text-secondary)]">Demo Mode</span>
        </div>
      </div>

      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {events.map((event, i) => (
          <div
            key={`${event.data.contradiction_id}-${i}`}
            className="flex items-center gap-3 rounded-lg bg-white/[0.03] p-3 text-xs"
          >
            <SeverityBadge severity={event.data.severity} />
            <span className="font-mono text-brand-400">
              {event.data.company_ticker}
            </span>
            <span className="text-[var(--text-secondary)]">
              #{event.data.contradiction_id}
            </span>
            <span className="ml-auto text-[var(--text-secondary)]">
              {new Date(event.timestamp).toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

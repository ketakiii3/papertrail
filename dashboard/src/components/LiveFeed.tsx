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

type FeedMode = "demo" | "live" | "connecting" | "offline";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "";

function wsFeedUrl(): string {
  const base = WS_BASE.replace(/\/$/, "");
  return `${base}/ws/feed`;
}

export default function LiveFeed() {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [mode, setMode] = useState<FeedMode>(WS_BASE ? "connecting" : "demo");

  useEffect(() => {
    if (!WS_BASE) {
      const now = Date.now();
      setEvents(
        DEMO_EVENTS.map((e, i) => ({
          ...e,
          timestamp: now - i * 180000,
        }))
      );
      setMode("demo");
      return;
    }

    let ws: WebSocket | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setMode("connecting");
      try {
        ws = new WebSocket(wsFeedUrl());
      } catch {
        setMode("offline");
        return;
      }

      ws.onopen = () => {
        if (!cancelled) setMode("live");
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string);
          if (msg.type !== "contradiction" || !msg.data) return;
          const d = msg.data as Record<string, unknown>;
          const id = Number(d.contradiction_id);
          if (Number.isNaN(id)) return;
          const ticker = typeof d.company_ticker === "string" ? d.company_ticker : "???";
          const severity = typeof d.severity === "string" ? d.severity : "medium";
          const row: FeedEvent = {
            type: "contradiction",
            data: { contradiction_id: id, company_ticker: ticker, severity },
            timestamp: Date.now(),
          };
          setEvents((prev) => [row, ...prev].slice(0, 40));
        } catch {
          /* ignore malformed messages */
        }
      };

      ws.onerror = () => {
        if (!cancelled) setMode("offline");
      };

      ws.onclose = () => {
        if (cancelled) return;
        setMode("offline");
      };
    };

    connect();

    return () => {
      cancelled = true;
      ws?.close();
    };
  }, []);

  const badge =
    mode === "demo" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-severity-low animate-pulse" />
        <span className="text-[11px] text-[var(--text-muted)]">Demo</span>
      </>
    ) : mode === "live" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-[11px] text-[var(--text-muted)]">Live</span>
      </>
    ) : mode === "connecting" ? (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
        <span className="text-[11px] text-[var(--text-muted)]">Connecting</span>
      </>
    ) : (
      <>
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-muted)]" />
        <span className="text-[11px] text-[var(--text-muted)]">Offline</span>
      </>
    );

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-sans text-[12px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
          Live Feed
        </h3>
        <div className="flex items-center gap-1.5">{badge}</div>
      </div>

      <div className="space-y-1 max-h-[300px] overflow-y-auto">
        {events.length === 0 && WS_BASE && mode !== "demo" ? (
          <p className="text-[13px] text-[var(--text-secondary)] py-6 text-center leading-relaxed">
            Connected — waiting for new contradictions from the pipeline. Nothing will appear here until the
            contradiction detector writes to the feed.
          </p>
        ) : (
          events.map((event, i) => (
            <div
              key={`${event.data.contradiction_id}-${event.timestamp}-${i}`}
              className="flex items-center gap-3 rounded-lg p-2.5 text-[12px] transition-colors hover:bg-[var(--bg-secondary)]"
            >
              <SeverityBadge severity={event.data.severity} />
              <span className="font-mono font-medium text-warm-700">
                {event.data.company_ticker}
              </span>
              <span className="text-[var(--text-muted)]">#{event.data.contradiction_id}</span>
              <span className="ml-auto text-[var(--text-muted)] text-[11px]">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

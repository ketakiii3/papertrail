"use client";

import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL || "";

interface Flag {
  id: number;
  transaction_id: number;
  ticker: string;
  company_name: string;
  insider_name: string;
  insider_title: string | null;
  transaction_type: string;
  transaction_date: string;
  shares: number | null;
  price: number | null;
  total_value: number | null;
  event_date: string;
  car: number | null;
  car_zscore: number | null;
  volume_ratio: number | null;
  flagged: boolean;
  flag_reason: string;
  computed_at: string;
}

interface FlagDetail extends Flag {
  baseline_alpha: number | null;
  baseline_beta: number | null;
  baseline_r2: number | null;
  daily_ar: { date: string; ret: number; expected: number; ar: number }[];
}

function fmtPct(v: number | null, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtNum(v: number | null, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function Sparkline({ data }: { data: { ar: number; date: string }[] }) {
  if (!data || data.length === 0) return <span className="text-[var(--text-muted)]">—</span>;
  return (
    <div className="h-8 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="ar"
            stroke="currentColor"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function SurveillancePanel() {
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [selected, setSelected] = useState<FlagDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    const url = `${API}/api/v1/surveillance/flags${onlyFlagged ? "?flagged=true" : ""}&limit=50`.replace("?&", "?");
    fetch(url)
      .then((r) => (r.ok ? r.json() : []))
      .then(setFlags)
      .catch(() => setFlags([]));
  }, [onlyFlagged]);

  const openDrawer = async (id: number) => {
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/api/v1/surveillance/flags/${id}`);
      if (res.ok) setSelected(await res.json());
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="font-serif text-2xl font-normal text-warm-950">
            Insider Trade Surveillance
          </h2>
          <p className="text-[13px] text-[var(--text-secondary)] mt-1">
            Event-study CAR + volume anomalies around Form 4 transactions.
          </p>
        </div>
        <button
          onClick={() => setOnlyFlagged((v) => !v)}
          className={`rounded-full border px-3 py-1 text-[12px] font-medium transition-colors ${
            onlyFlagged
              ? "border-accent-500 bg-accent-50 text-accent-500"
              : "border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)]"
          }`}
        >
          {onlyFlagged ? "Showing flagged" : "Show all"}
        </button>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] overflow-hidden">
        {flags === null ? (
          <div className="p-8 text-center text-[13px] text-[var(--text-muted)]">Loading…</div>
        ) : flags.length === 0 ? (
          <div className="p-8 text-center text-[13px] text-[var(--text-muted)]">
            No surveillance flags yet. They appear after Form 4 ingestion runs.
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-[var(--bg-secondary)] text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Ticker</th>
                <th className="px-4 py-2.5 text-left font-medium">Insider</th>
                <th className="px-4 py-2.5 text-left font-medium">Trade</th>
                <th className="px-4 py-2.5 text-right font-medium">CAR [0,+5]</th>
                <th className="px-4 py-2.5 text-right font-medium">z</th>
                <th className="px-4 py-2.5 text-right font-medium">Vol×</th>
                <th className="px-4 py-2.5 text-left font-medium">Flag</th>
              </tr>
            </thead>
            <tbody>
              {flags.map((f) => (
                <tr
                  key={f.id}
                  onClick={() => openDrawer(f.id)}
                  className="cursor-pointer border-t border-[var(--border)] transition-colors hover:bg-[var(--bg-secondary)]"
                >
                  <td className="px-4 py-2.5 font-mono font-medium text-warm-700">{f.ticker}</td>
                  <td className="px-4 py-2.5 text-warm-800">
                    <div>{f.insider_name}</div>
                    {f.insider_title && (
                      <div className="text-[11px] text-[var(--text-muted)]">{f.insider_title}</div>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[var(--text-secondary)]">
                    <span className={f.transaction_type === "P" ? "text-emerald-600" : "text-rose-600"}>
                      {f.transaction_type === "P" ? "BUY" : f.transaction_type === "S" ? "SELL" : f.transaction_type}
                    </span>{" "}
                    <span className="text-[11px] text-[var(--text-muted)]">{f.transaction_date}</span>
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${
                    f.car !== null && f.car >= 0 ? "text-emerald-600" : "text-rose-600"
                  }`}>
                    {fmtPct(f.car)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-warm-800">{fmtNum(f.car_zscore)}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-warm-800">{fmtNum(f.volume_ratio)}×</td>
                  <td className="px-4 py-2.5">
                    {f.flagged ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                        flagged
                      </span>
                    ) : (
                      <span className="text-[11px] text-[var(--text-muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div
          className="fixed inset-0 z-50 bg-black/30"
          onClick={() => setSelected(null)}
        >
          <div
            className="absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto bg-[var(--bg-card)] shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--border)] p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-mono text-[13px] text-[var(--text-muted)]">
                    {selected.ticker} · {selected.event_date}
                  </div>
                  <h3 className="font-serif text-2xl font-light italic text-warm-950 mt-1">
                    {selected.insider_name}
                  </h3>
                  {selected.insider_title && (
                    <div className="text-[13px] text-[var(--text-secondary)]">{selected.insider_title}</div>
                  )}
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="text-[var(--text-muted)] hover:text-warm-700"
                >
                  ✕
                </button>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-4 text-[13px]">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">CAR</div>
                  <div className={`font-mono text-lg ${
                    selected.car !== null && selected.car >= 0 ? "text-emerald-600" : "text-rose-600"
                  }`}>
                    {fmtPct(selected.car)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">z-score</div>
                  <div className="font-mono text-lg text-warm-800">{fmtNum(selected.car_zscore)}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Vol ratio</div>
                  <div className="font-mono text-lg text-warm-800">{fmtNum(selected.volume_ratio)}×</div>
                </div>
              </div>

              <div className="mt-3 text-[12px] text-[var(--text-secondary)]">
                {selected.flagged ? (
                  <span className="text-rose-700">⚑ {selected.flag_reason}</span>
                ) : (
                  <span>{selected.flag_reason}</span>
                )}
              </div>
            </div>

            <div className="p-6">
              <h4 className="text-[12px] font-medium uppercase tracking-wide text-[var(--text-muted)] mb-3">
                Daily abnormal returns
              </h4>
              {loadingDetail ? (
                <div className="text-[13px] text-[var(--text-muted)]">Loading…</div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={selected.daily_ar}>
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} />
                      <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                      <Tooltip
                        formatter={(v) => typeof v === "number" ? `${(v * 100).toFixed(2)}%` : String(v)}
                        labelStyle={{ fontSize: 12 }}
                      />
                      <Line type="monotone" dataKey="ar" stroke="#dc2626" strokeWidth={2} name="AR" />
                      <Line type="monotone" dataKey="ret" stroke="#2563eb" strokeWidth={1} dot={false} name="Realized" />
                      <Line type="monotone" dataKey="expected" stroke="#9ca3af" strokeWidth={1} dot={false} name="Expected" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="mt-6 grid grid-cols-2 gap-4 text-[12px]">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Market model</div>
                  <div className="font-mono text-warm-800 mt-1">
                    α = {fmtNum(selected.baseline_alpha, 5)}<br />
                    β = {fmtNum(selected.baseline_beta, 3)}<br />
                    R² = {fmtNum(selected.baseline_r2, 3)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Trade</div>
                  <div className="font-mono text-warm-800 mt-1">
                    {selected.transaction_type === "P" ? "BUY" : "SELL"} · {selected.shares?.toLocaleString()} sh<br />
                    @ ${selected.price?.toFixed(2)}<br />
                    {selected.total_value && `$${(selected.total_value / 1_000_000).toFixed(1)}M`}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

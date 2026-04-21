"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<
    { ticker: string; name: string; id: number }[]
  >([]);
  const [isOpen, setIsOpen] = useState(false);
  const router = useRouter();

  const search = useCallback(async (q: string) => {
    if (q.length < 1) {
      setResults([]);
      return;
    }
    try {
      const API = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${API}/api/v1/companies?search=${q}&limit=8`);
      if (res.ok) {
        setResults(await res.json());
      }
    } catch {
      // API not available
    }
  }, []);

  return (
    <div className="relative w-full max-w-lg" id="search">
      <div className="relative">
        <svg
          className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            search(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => setTimeout(() => setIsOpen(false), 200)}
          placeholder="Search by company ticker or name..."
          className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-2.5 pl-10 pr-4 text-[14px] text-warm-900 outline-none transition-all focus:border-[var(--border-hover)] focus:ring-2 focus:ring-accent-500/25"
        />
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute z-50 mt-1.5 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] shadow-lg shadow-black/40">
          {results.map((company) => (
            <button
              key={company.id}
              onClick={() => {
                router.push(`/company/${company.ticker}`);
                setIsOpen(false);
                setQuery("");
              }}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[var(--bg-secondary)] first:rounded-t-xl last:rounded-b-xl"
            >
              <span className="rounded border border-[var(--border)] bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px] font-semibold tracking-wide text-warm-700">
                {company.ticker}
              </span>
              <span className="text-[14px] text-warm-600">{company.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

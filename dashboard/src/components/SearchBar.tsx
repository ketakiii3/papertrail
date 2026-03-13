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
    <div className="relative w-full max-w-xl" id="search">
      <div className="relative">
        <svg
          className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-secondary)]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
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
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] py-3 pl-10 pr-4 text-sm text-white placeholder-[var(--text-secondary)] outline-none transition-colors focus:border-brand-500/50 focus:bg-white/[0.06]"
        />
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute z-50 mt-2 w-full rounded-xl border border-white/10 bg-[var(--bg-secondary)] shadow-2xl">
          {results.map((company) => (
            <button
              key={company.id}
              onClick={() => {
                router.push(`/company/${company.ticker}`);
                setIsOpen(false);
                setQuery("");
              }}
              className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/5 first:rounded-t-xl last:rounded-b-xl"
            >
              <span className="rounded bg-brand-600/20 px-2 py-0.5 text-xs font-bold text-brand-400">
                {company.ticker}
              </span>
              <span className="text-sm">{company.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

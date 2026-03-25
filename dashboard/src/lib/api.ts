const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchAPI<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Types
export interface Company {
  id: number;
  ticker: string;
  name: string;
  sector: string | null;
}

export interface Claim {
  id: number;
  filing_id: number;
  claim_text: string;
  claim_type: string | null;
  topic: string | null;
  sentiment: string | null;
  confidence: number | null;
  entities: Record<string, string[]> | null;
  temporal_ref: string | null;
  source_section: string | null;
  claim_date: string | null;
}

export interface Contradiction {
  id: number;
  company_ticker: string;
  company_name: string;
  claim_a: Claim;
  claim_b: Claim;
  similarity_score: number;
  nli_contradiction_score: number;
  severity: "low" | "medium" | "high" | "critical";
  time_gap_days: number | null;
  explanation: string | null;
  agent_reasoning: string | null;
  created_at: string | null;
}

export interface TimelineEvent {
  type: "filing" | "contradiction";
  date: string;
  data: Record<string, any>;
}

export interface Timeline {
  ticker: string;
  company_name: string;
  events: TimelineEvent[];
}

export interface Stats {
  total_companies: number;
  total_filings: number;
  total_claims: number;
  total_contradictions: number;
  contradictions_by_severity: Record<string, number>;
}

// API functions
export const api = {
  getCompanies: (search?: string) =>
    fetchAPI<Company[]>(`/api/v1/companies${search ? `?search=${search}` : ""}`),

  getCompany: (ticker: string) =>
    fetchAPI<Company>(`/api/v1/companies/${ticker}`),

  getTimeline: (ticker: string) =>
    fetchAPI<Timeline>(`/api/v1/companies/${ticker}/timeline`),

  getContradictions: (ticker: string, severity?: string) =>
    fetchAPI<Contradiction[]>(
      `/api/v1/companies/${ticker}/contradictions${severity ? `?severity=${severity}` : ""}`
    ),

  getClaims: (ticker: string, params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchAPI<Claim[]>(`/api/v1/companies/${ticker}/claims${qs}`);
  },

  getLatestContradictions: (severity?: string) =>
    fetchAPI<Contradiction[]>(
      `/api/v1/contradictions/latest${severity ? `?severity=${severity}` : ""}`
    ),

  searchClaims: (query: string) =>
    fetchAPI<{ claim: Claim; similarity: number; company_ticker: string }[]>(
      `/api/v1/search/claims?q=${encodeURIComponent(query)}`
    ),

  getStats: () => fetchAPI<Stats>("/api/v1/stats"),

  addToWatchlist: (email: string, ticker: string) =>
    fetch(`${API_URL}/api/v1/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, ticker }),
    }),
};

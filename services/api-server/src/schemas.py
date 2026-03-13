"""API response schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class CompanyResponse(BaseModel):
    id: int
    ticker: str
    name: str
    sector: Optional[str] = None


class FilingResponse(BaseModel):
    id: int
    form_type: str
    filed_at: date
    period_of_report: Optional[date] = None
    url: str
    claim_count: int = 0


class ClaimResponse(BaseModel):
    id: int
    filing_id: int
    claim_text: str
    claim_type: Optional[str] = None
    topic: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    entities: Optional[dict] = None
    temporal_ref: Optional[str] = None
    source_section: Optional[str] = None
    claim_date: Optional[date] = None


class ContradictionResponse(BaseModel):
    id: int
    company_ticker: str
    company_name: str
    claim_a: ClaimResponse
    claim_b: ClaimResponse
    similarity_score: float
    nli_contradiction_score: float
    severity: str
    time_gap_days: Optional[int] = None
    explanation: Optional[str] = None
    created_at: Optional[datetime] = None


class TimelineEvent(BaseModel):
    type: str  # "filing" or "contradiction"
    date: date
    data: dict


class TimelineResponse(BaseModel):
    ticker: str
    company_name: str
    events: list[TimelineEvent]


class SearchResult(BaseModel):
    claim: ClaimResponse
    similarity: float
    company_ticker: str


class StatsResponse(BaseModel):
    total_companies: int
    total_filings: int
    total_claims: int
    total_contradictions: int
    contradictions_by_severity: dict


class WatchlistRequest(BaseModel):
    email: str
    ticker: str

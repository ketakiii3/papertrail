"""API response schemas."""

import json
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator


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
    # JSONB may decode as dict, list, or nested structures — avoid 500 on response validation
    entities: Optional[Any] = None
    temporal_ref: Optional[str] = None
    source_section: Optional[str] = None
    claim_date: Optional[date] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence_to_float(cls, v):
        if v is None:
            return None
        return float(v)

    @field_validator("entities", mode="before")
    @classmethod
    def _entities_from_db(cls, v):
        # asyncpg sometimes returns JSONB as str depending on driver/column typing
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                parsed = json.loads(s)
                return parsed if isinstance(parsed, (dict, list)) else {"value": parsed}
            except json.JSONDecodeError:
                return {"raw": s}
        return v


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
    agent_reasoning: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("similarity_score", "nli_contradiction_score", mode="before")
    @classmethod
    def _scores_to_float(cls, v):
        return float(v) if v is not None else 0.0


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

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ClaimType(str, Enum):
    GUIDANCE = "guidance"
    RISK = "risk"
    STRATEGY = "strategy"
    FACTUAL = "factual"
    OPINION = "opinion"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class Company(BaseModel):
    id: int
    ticker: str
    name: str
    cik: str
    sector: Optional[str] = None
    industry: Optional[str] = None


class Filing(BaseModel):
    id: int
    company_id: int
    accession_number: str
    form_type: str
    filed_at: date
    period_of_report: Optional[date] = None
    url: str
    processed: bool = False
    created_at: Optional[datetime] = None


class Claim(BaseModel):
    id: int
    filing_id: int
    company_id: int
    speaker: Optional[str] = None
    claim_text: str
    claim_type: Optional[str] = None
    topic: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    entities: Optional[dict] = None
    temporal_ref: Optional[str] = None
    source_section: Optional[str] = None
    claim_date: Optional[date] = None
    created_at: Optional[datetime] = None


class Contradiction(BaseModel):
    id: int
    claim_a_id: int
    claim_b_id: int
    company_id: int
    similarity_score: float
    nli_contradiction_score: float
    severity: str
    time_gap_days: Optional[int] = None
    explanation: Optional[str] = None
    agent_reasoning: Optional[str] = None
    created_at: Optional[datetime] = None


class InsiderTransaction(BaseModel):
    id: int
    company_id: int
    insider_name: str
    insider_title: Optional[str] = None
    transaction_type: str
    shares: Optional[int] = None
    price: Optional[float] = None
    total_value: Optional[float] = None
    transaction_date: date
    filing_date: date

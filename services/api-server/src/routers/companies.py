"""Company endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from shared.db import get_pool
from src.schemas import (
    CompanyResponse, FilingResponse, ClaimResponse,
    ContradictionResponse, TimelineResponse, TimelineEvent,
)

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    search: Optional[str] = Query(None, description="Search by ticker or name"),
    limit: int = Query(50, le=500),
):
    pool = await get_pool()
    if search:
        rows = await pool.fetch(
            """SELECT id, ticker, name, sector FROM companies
               WHERE ticker ILIKE $1 OR name ILIKE $1
               ORDER BY ticker LIMIT $2""",
            f"%{search}%", limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, ticker, name, sector FROM companies ORDER BY ticker LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/{ticker}", response_model=CompanyResponse)
async def get_company(ticker: str):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, ticker, name, sector FROM companies WHERE ticker = $1",
        ticker.upper(),
    )
    if not row:
        raise HTTPException(404, f"Company {ticker} not found")
    return dict(row)


@router.get("/{ticker}/timeline", response_model=TimelineResponse)
async def get_timeline(
    ticker: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    pool = await get_pool()
    company = await pool.fetchrow(
        "SELECT id, ticker, name FROM companies WHERE ticker = $1",
        ticker.upper(),
    )
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")

    events = []

    # Get filings
    query = """
        SELECT f.id, f.form_type, f.filed_at, f.url,
               COUNT(c.id) as claim_count
        FROM filings f
        LEFT JOIN claims c ON c.filing_id = f.id
        WHERE f.company_id = $1
    """
    params = [company["id"]]
    idx = 2

    if start_date:
        query += f" AND f.filed_at >= ${idx}"
        params.append(start_date)
        idx += 1
    if end_date:
        query += f" AND f.filed_at <= ${idx}"
        params.append(end_date)
        idx += 1

    query += " GROUP BY f.id ORDER BY f.filed_at DESC"
    filings = await pool.fetch(query, *params)

    for f in filings:
        events.append(TimelineEvent(
            type="filing",
            date=f["filed_at"],
            data={
                "id": f["id"],
                "form_type": f["form_type"],
                "url": f["url"],
                "claim_count": f["claim_count"],
            },
        ))

    # Get contradictions
    contradictions = await pool.fetch(
        """SELECT con.id, con.severity, con.created_at::date as date,
                  con.similarity_score, con.nli_contradiction_score,
                  ca.claim_text as claim_a_text, ca.claim_date as claim_a_date,
                  cb.claim_text as claim_b_text, cb.claim_date as claim_b_date
           FROM contradictions con
           JOIN claims ca ON ca.id = con.claim_a_id
           JOIN claims cb ON cb.id = con.claim_b_id
           WHERE con.company_id = $1
           ORDER BY con.created_at DESC""",
        company["id"],
    )

    for c in contradictions:
        events.append(TimelineEvent(
            type="contradiction",
            date=c["date"],
            data={
                "id": c["id"],
                "severity": c["severity"],
                "similarity_score": c["similarity_score"],
                "claim_a_text": c["claim_a_text"][:200],
                "claim_b_text": c["claim_b_text"][:200],
                "claim_a_date": str(c["claim_a_date"]) if c["claim_a_date"] else None,
                "claim_b_date": str(c["claim_b_date"]) if c["claim_b_date"] else None,
            },
        ))

    events.sort(key=lambda e: e.date, reverse=True)

    return TimelineResponse(
        ticker=company["ticker"],
        company_name=company["name"],
        events=events,
    )


@router.get("/{ticker}/contradictions", response_model=list[ContradictionResponse])
async def get_contradictions(
    ticker: str,
    severity: Optional[str] = None,
    topic: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    pool = await get_pool()
    company = await pool.fetchrow(
        "SELECT id, ticker, name FROM companies WHERE ticker = $1",
        ticker.upper(),
    )
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")

    query = """
        SELECT con.id, con.similarity_score, con.nli_contradiction_score,
               con.severity, con.time_gap_days, con.explanation, con.created_at,
               ca.id as ca_id, ca.filing_id as ca_filing_id, ca.claim_text as ca_text,
               ca.claim_type as ca_type, ca.topic as ca_topic, ca.sentiment as ca_sentiment,
               ca.confidence as ca_confidence, ca.entities as ca_entities,
               ca.temporal_ref as ca_temporal_ref, ca.source_section as ca_section,
               ca.claim_date as ca_date,
               cb.id as cb_id, cb.filing_id as cb_filing_id, cb.claim_text as cb_text,
               cb.claim_type as cb_type, cb.topic as cb_topic, cb.sentiment as cb_sentiment,
               cb.confidence as cb_confidence, cb.entities as cb_entities,
               cb.temporal_ref as cb_temporal_ref, cb.source_section as cb_section,
               cb.claim_date as cb_date
        FROM contradictions con
        JOIN claims ca ON ca.id = con.claim_a_id
        JOIN claims cb ON cb.id = con.claim_b_id
        WHERE con.company_id = $1
    """
    params = [company["id"]]
    idx = 2

    if severity:
        query += f" AND con.severity = ${idx}"
        params.append(severity)
        idx += 1
    if topic:
        query += f" AND (ca.topic = ${idx} OR cb.topic = ${idx})"
        params.append(topic)
        idx += 1

    query += f" ORDER BY con.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    rows = await pool.fetch(query, *params)

    results = []
    for r in rows:
        results.append(ContradictionResponse(
            id=r["id"],
            company_ticker=company["ticker"],
            company_name=company["name"],
            claim_a=ClaimResponse(
                id=r["ca_id"], filing_id=r["ca_filing_id"], claim_text=r["ca_text"],
                claim_type=r["ca_type"], topic=r["ca_topic"], sentiment=r["ca_sentiment"],
                confidence=r["ca_confidence"], entities=r["ca_entities"],
                temporal_ref=r["ca_temporal_ref"], source_section=r["ca_section"],
                claim_date=r["ca_date"],
            ),
            claim_b=ClaimResponse(
                id=r["cb_id"], filing_id=r["cb_filing_id"], claim_text=r["cb_text"],
                claim_type=r["cb_type"], topic=r["cb_topic"], sentiment=r["cb_sentiment"],
                confidence=r["cb_confidence"], entities=r["cb_entities"],
                temporal_ref=r["cb_temporal_ref"], source_section=r["cb_section"],
                claim_date=r["cb_date"],
            ),
            similarity_score=r["similarity_score"],
            nli_contradiction_score=r["nli_contradiction_score"],
            severity=r["severity"],
            time_gap_days=r["time_gap_days"],
            explanation=r["explanation"],
            created_at=r["created_at"],
        ))

    return results


@router.get("/{ticker}/claims", response_model=list[ClaimResponse])
async def get_claims(
    ticker: str,
    claim_type: Optional[str] = None,
    topic: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    pool = await get_pool()
    company = await pool.fetchrow(
        "SELECT id FROM companies WHERE ticker = $1", ticker.upper(),
    )
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")

    query = """
        SELECT id, filing_id, claim_text, claim_type, topic, sentiment,
               confidence, entities, temporal_ref, source_section, claim_date
        FROM claims WHERE company_id = $1
    """
    params = [company["id"]]
    idx = 2

    if claim_type:
        query += f" AND claim_type = ${idx}"
        params.append(claim_type)
        idx += 1
    if topic:
        query += f" AND topic = ${idx}"
        params.append(topic)
        idx += 1
    if sentiment:
        query += f" AND sentiment = ${idx}"
        params.append(sentiment)
        idx += 1

    query += f" ORDER BY claim_date DESC NULLS LAST LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    rows = await pool.fetch(query, *params)
    return [dict(r) for r in rows]

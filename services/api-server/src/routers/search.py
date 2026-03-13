"""Search and global contradiction endpoints."""

from typing import Optional

from fastapi import APIRouter, Query

from shared.db import get_pool
from src.schemas import ContradictionResponse, ClaimResponse, SearchResult, StatsResponse

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search/claims", response_model=list[SearchResult])
async def search_claims(
    q: str = Query(..., min_length=3, description="Search query"),
    limit: int = Query(20, le=100),
):
    """Semantic search across all claims using pgvector similarity."""
    pool = await get_pool()

    # For MVP, use text search. Full semantic search requires embedding the query.
    rows = await pool.fetch(
        """SELECT c.id, c.filing_id, c.claim_text, c.claim_type, c.topic,
                  c.sentiment, c.confidence, c.entities, c.temporal_ref,
                  c.source_section, c.claim_date,
                  co.ticker,
                  1.0 as similarity
           FROM claims c
           JOIN companies co ON co.id = c.company_id
           WHERE c.claim_text ILIKE $1
           ORDER BY c.claim_date DESC NULLS LAST
           LIMIT $2""",
        f"%{q}%", limit,
    )

    results = []
    for r in rows:
        results.append(SearchResult(
            claim=ClaimResponse(
                id=r["id"], filing_id=r["filing_id"], claim_text=r["claim_text"],
                claim_type=r["claim_type"], topic=r["topic"], sentiment=r["sentiment"],
                confidence=r["confidence"], entities=r["entities"],
                temporal_ref=r["temporal_ref"], source_section=r["source_section"],
                claim_date=r["claim_date"],
            ),
            similarity=r["similarity"],
            company_ticker=r["ticker"],
        ))

    return results


@router.get("/contradictions/latest", response_model=list[ContradictionResponse])
async def get_latest_contradictions(
    severity: Optional[str] = None,
    limit: int = Query(20, le=100),
):
    """Latest contradictions across all S&P 500 companies."""
    pool = await get_pool()

    query = """
        SELECT con.id, con.similarity_score, con.nli_contradiction_score,
               con.severity, con.time_gap_days, con.explanation, con.created_at,
               co.ticker, co.name as company_name,
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
        JOIN companies co ON co.id = con.company_id
    """
    params = []
    idx = 1

    if severity:
        query += f" WHERE con.severity = ${idx}"
        params.append(severity)
        idx += 1

    query += f" ORDER BY con.created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await pool.fetch(query, *params)

    results = []
    for r in rows:
        results.append(ContradictionResponse(
            id=r["id"],
            company_ticker=r["ticker"],
            company_name=r["company_name"],
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


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get system-wide statistics."""
    pool = await get_pool()

    total_companies = await pool.fetchval("SELECT COUNT(*) FROM companies")
    total_filings = await pool.fetchval("SELECT COUNT(*) FROM filings")
    total_claims = await pool.fetchval("SELECT COUNT(*) FROM claims")
    total_contradictions = await pool.fetchval("SELECT COUNT(*) FROM contradictions")

    severity_rows = await pool.fetch(
        "SELECT severity, COUNT(*) as count FROM contradictions GROUP BY severity"
    )
    contradictions_by_severity = {r["severity"]: r["count"] for r in severity_rows}

    return StatsResponse(
        total_companies=total_companies,
        total_filings=total_filings,
        total_claims=total_claims,
        total_contradictions=total_contradictions,
        contradictions_by_severity=contradictions_by_severity,
    )

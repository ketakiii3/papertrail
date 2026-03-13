"""Filing diff and insider transaction endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from shared.db import get_pool

router = APIRouter(prefix="/api/v1/companies", tags=["filings"])


@router.get("/{ticker}/filings/{filing_id}/diff")
async def get_filing_diff(ticker: str, filing_id: int):
    """Semantic diff: compare claims in this filing vs the previous filing of the same type."""
    pool = await get_pool()

    company = await pool.fetchrow(
        "SELECT id FROM companies WHERE ticker = $1", ticker.upper()
    )
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")

    # Get this filing
    filing = await pool.fetchrow(
        "SELECT id, form_type, filed_at FROM filings WHERE id = $1 AND company_id = $2",
        filing_id, company["id"],
    )
    if not filing:
        raise HTTPException(404, f"Filing {filing_id} not found")

    # Find the previous filing of the same type
    prev_filing = await pool.fetchrow(
        """SELECT id, form_type, filed_at FROM filings
           WHERE company_id = $1 AND form_type = $2 AND filed_at < $3
           ORDER BY filed_at DESC LIMIT 1""",
        company["id"], filing["form_type"], filing["filed_at"],
    )

    if not prev_filing:
        return {
            "filing_id": filing_id,
            "form_type": filing["form_type"],
            "filed_at": str(filing["filed_at"]),
            "previous_filing": None,
            "message": "No previous filing of this type found for comparison",
            "new_claims": [],
            "removed_topics": [],
            "changed_claims": [],
        }

    # Get claims from both filings
    current_claims = await pool.fetch(
        """SELECT id, claim_text, claim_type, topic, sentiment, confidence, source_section
           FROM claims WHERE filing_id = $1 ORDER BY id""",
        filing_id,
    )
    prev_claims = await pool.fetch(
        """SELECT id, claim_text, claim_type, topic, sentiment, confidence, source_section
           FROM claims WHERE filing_id = $1 ORDER BY id""",
        prev_filing["id"],
    )

    # Compare by topic - find new, removed, and changed topics
    current_topics = {c["topic"] for c in current_claims if c["topic"]}
    prev_topics = {c["topic"] for c in prev_claims if c["topic"]}

    new_topics = current_topics - prev_topics
    removed_topics = prev_topics - current_topics

    # Find claims in new topics
    new_claims = [
        dict(c) for c in current_claims if c["topic"] in new_topics
    ]

    # Find claims with sentiment changes on same topics
    changed_claims = []
    for topic in current_topics & prev_topics:
        curr_by_topic = [c for c in current_claims if c["topic"] == topic]
        prev_by_topic = [c for c in prev_claims if c["topic"] == topic]

        for cc in curr_by_topic:
            for pc in prev_by_topic:
                if cc["sentiment"] != pc["sentiment"] and cc["source_section"] == pc["source_section"]:
                    changed_claims.append({
                        "topic": topic,
                        "section": cc["source_section"],
                        "previous": {
                            "claim_text": pc["claim_text"],
                            "sentiment": pc["sentiment"],
                        },
                        "current": {
                            "claim_text": cc["claim_text"],
                            "sentiment": cc["sentiment"],
                        },
                    })

    # Detect risk factor changes (Item 1A specific)
    current_risks = [c for c in current_claims if c["source_section"] and "1A" in c["source_section"]]
    prev_risks = [c for c in prev_claims if c["source_section"] and "1A" in c["source_section"]]

    risk_changes = {
        "new_risk_factors": len(current_risks) - len(prev_risks) if len(current_risks) > len(prev_risks) else 0,
        "removed_risk_factors": len(prev_risks) - len(current_risks) if len(prev_risks) > len(current_risks) else 0,
        "current_count": len(current_risks),
        "previous_count": len(prev_risks),
    }

    return {
        "filing_id": filing_id,
        "form_type": filing["form_type"],
        "filed_at": str(filing["filed_at"]),
        "previous_filing": {
            "id": prev_filing["id"],
            "filed_at": str(prev_filing["filed_at"]),
        },
        "summary": {
            "current_claims": len(current_claims),
            "previous_claims": len(prev_claims),
            "new_topics": list(new_topics),
            "removed_topics": list(removed_topics),
            "sentiment_changes": len(changed_claims),
        },
        "risk_factor_changes": risk_changes,
        "new_claims": new_claims[:50],
        "changed_claims": changed_claims[:50],
    }


@router.get("/{ticker}/insiders")
async def get_insider_transactions(
    ticker: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    transaction_type: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """Get insider transactions with optional contradiction context overlay."""
    pool = await get_pool()

    company = await pool.fetchrow(
        "SELECT id FROM companies WHERE ticker = $1", ticker.upper()
    )
    if not company:
        raise HTTPException(404, f"Company {ticker} not found")

    query = """
        SELECT id, insider_name, insider_title, transaction_type,
               shares, price, total_value, transaction_date, filing_date
        FROM insider_transactions
        WHERE company_id = $1
    """
    params = [company["id"]]
    idx = 2

    if start_date:
        query += f" AND transaction_date >= ${idx}"
        params.append(start_date)
        idx += 1
    if end_date:
        query += f" AND transaction_date <= ${idx}"
        params.append(end_date)
        idx += 1
    if transaction_type:
        query += f" AND transaction_type = ${idx}"
        params.append(transaction_type)
        idx += 1

    query += f" ORDER BY transaction_date DESC LIMIT ${idx}"
    params.append(limit)

    transactions = await pool.fetch(query, *params)

    # For each transaction, check if it falls between any contradiction claim dates
    results = []
    for t in transactions:
        t_dict = dict(t)

        # Find contradictions where this trade happened between claim_a and claim_b dates
        overlapping = await pool.fetch(
            """SELECT con.id, con.severity, ca.claim_text as claim_a_text,
                      cb.claim_text as claim_b_text, ca.claim_date as claim_a_date,
                      cb.claim_date as claim_b_date
               FROM contradictions con
               JOIN claims ca ON ca.id = con.claim_a_id
               JOIN claims cb ON cb.id = con.claim_b_id
               WHERE con.company_id = $1
                 AND ca.claim_date <= $2
                 AND cb.claim_date >= $2""",
            company["id"], t["transaction_date"],
        )

        t_dict["related_contradictions"] = [dict(o) for o in overlapping]
        t_dict["suspicious"] = (
            t["transaction_type"] == "sell"
            and len(overlapping) > 0
            and any(o["severity"] in ("high", "critical") for o in overlapping)
        )
        results.append(t_dict)

    return results

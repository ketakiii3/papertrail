"""Graph builder consumer - syncs PostgreSQL data to Neo4j."""

import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from shared.db import get_pool
from shared.redis_client import create_consumer_group, consume_events
from .graph import Neo4jClient

logger = logging.getLogger(__name__)


async def sync_claims_to_graph(client: Neo4jClient, filing_id: int, company_id: int):
    """Fetch claims from PostgreSQL and insert into Neo4j."""
    pool = await get_pool()

    # Get company info
    company = await pool.fetchrow("SELECT ticker, name, sector FROM companies WHERE id = $1", company_id)
    if not company:
        return

    client.upsert_company(company["ticker"], company["name"], company.get("sector"))

    # Get filing info
    filing = await pool.fetchrow(
        "SELECT id, form_type, filed_at, url FROM filings WHERE id = $1", filing_id
    )
    if not filing:
        return

    client.upsert_filing(
        filing_id=filing["id"],
        form_type=filing["form_type"],
        filed_at=str(filing["filed_at"]),
        url=filing["url"],
        company_ticker=company["ticker"],
    )

    # Get claims
    claims = await pool.fetch(
        """SELECT id, claim_text, claim_type, topic, sentiment, confidence,
                  claim_date, speaker
           FROM claims WHERE filing_id = $1""",
        filing_id,
    )

    for claim in claims:
        client.upsert_claim(
            claim_id=claim["id"],
            text=claim["claim_text"],
            claim_type=claim["claim_type"] or "unknown",
            topic=claim["topic"] or "general",
            sentiment=claim["sentiment"] or "neutral",
            confidence=claim["confidence"] or 0.0,
            claim_date=str(claim["claim_date"]) if claim["claim_date"] else "",
            company_ticker=company["ticker"],
            filing_id=filing_id,
            speaker=claim["speaker"],
        )

    logger.info(f"Synced {len(claims)} claims to Neo4j for filing {filing_id}")


async def sync_contradiction_to_graph(client: Neo4jClient, contradiction_id: int):
    """Sync a contradiction edge to Neo4j."""
    pool = await get_pool()

    row = await pool.fetchrow(
        """SELECT claim_a_id, claim_b_id, similarity_score,
                  nli_contradiction_score, severity, time_gap_days
           FROM contradictions WHERE id = $1""",
        contradiction_id,
    )
    if not row:
        return

    client.add_contradiction_edge(
        claim_a_id=row["claim_a_id"],
        claim_b_id=row["claim_b_id"],
        severity=row["severity"],
        similarity=row["similarity_score"],
        nli_score=row["nli_contradiction_score"],
        time_gap_days=row["time_gap_days"],
    )
    logger.info(f"Synced contradiction {contradiction_id} to Neo4j")


async def run_consumer():
    """Listen for events and sync to Neo4j."""
    client = Neo4jClient()
    client.setup_schema()

    # Create consumer groups
    await create_consumer_group("claims.extracted", "graph-builders")
    await create_consumer_group("contradiction.found", "graph-builders")

    logger.info("Graph builder consumer started")

    try:
        while True:
            # Process claim events
            try:
                events = await consume_events(
                    "claims.extracted", "graph-builders", "builder-1", count=10
                )
                for msg_id, data in events:
                    await sync_claims_to_graph(client, data["filing_id"], data["company_id"])
            except Exception as e:
                logger.error(f"Error processing claims: {e}")

            # Process contradiction events
            try:
                events = await consume_events(
                    "contradiction.found", "graph-builders", "builder-1", count=10
                )
                for msg_id, data in events:
                    await sync_contradiction_to_graph(client, data["contradiction_id"])
            except Exception as e:
                logger.error(f"Error processing contradictions: {e}")

            await asyncio.sleep(0.1)
    finally:
        client.close()

"""Graph builder consumer - syncs PostgreSQL data to Neo4j."""

import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from shared.db import get_pool
from shared.kafka_client import consume
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


async def sync_insider_traded(client: Neo4jClient, transaction_id: int) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """SELECT t.id, t.insider_name, t.transaction_type,
                  t.shares, t.price, t.total_value, t.transaction_date,
                  c.ticker, c.name AS company_name, c.sector
           FROM insider_transactions t
           JOIN companies c ON c.id = t.company_id
           WHERE t.id = $1""",
        transaction_id,
    )
    if not row:
        logger.warning(f"insider.new for unknown transaction_id={transaction_id}")
        return
    client.upsert_company(row["ticker"], row["company_name"], row["sector"])
    client.upsert_insider_traded(
        transaction_id=row["id"],
        insider_name=row["insider_name"],
        ticker=row["ticker"],
        transaction_type=row["transaction_type"],
        shares=row["shares"],
        price=float(row["price"]) if row["price"] is not None else None,
        total_value=float(row["total_value"]) if row["total_value"] is not None else None,
        transaction_date=str(row["transaction_date"]),
    )
    logger.info(f"TRADED edge upserted for txn {transaction_id} ({row['insider_name']} -> {row['ticker']})")


async def sync_anomalous_movement(client: Neo4jClient, payload: dict) -> None:
    if not payload.get("flagged"):
        return  # only flagged events become graph edges
    client.upsert_anomalous_movement(
        transaction_id=payload["transaction_id"],
        insider_name=payload["insider_name"],
        ticker=payload["ticker"],
        car=payload["car"],
        car_zscore=payload["car_zscore"],
        volume_ratio=payload["volume_ratio"],
        event_date=payload["event_date"],
    )
    logger.info(
        f"ANOMALOUS_MOVEMENT upserted for txn {payload['transaction_id']} "
        f"({payload['insider_name']} -> {payload['ticker']}, "
        f"CAR={payload['car']:+.4f}, z={payload['car_zscore']:+.2f})"
    )


async def run_consumer():
    """Kafka consumers (one per topic) syncing into Neo4j."""
    client = Neo4jClient()
    client.setup_schema()

    async def handle_claims(data: dict) -> None:
        await sync_claims_to_graph(client, data["filing_id"], data["company_id"])

    async def handle_contradictions(data: dict) -> None:
        await sync_contradiction_to_graph(client, data["contradiction_id"])

    async def handle_insider(data: dict) -> None:
        await sync_insider_traded(client, data["transaction_id"])

    async def handle_flag(data: dict) -> None:
        await sync_anomalous_movement(client, data)

    logger.info("Graph builder consumer started")

    try:
        await asyncio.gather(
            consume("claims.extracted", "graph-builders", handle_claims),
            consume("contradiction.found", "graph-builders", handle_contradictions),
            consume("insider.new", "graph-builders", handle_insider),
            consume("surveillance.flag", "graph-builders", handle_flag),
        )
    finally:
        client.close()

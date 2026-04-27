"""Main contradiction detection pipeline."""

import logging
import sys

sys.path.insert(0, "/app")

from shared.db import get_pool, get_similar_claims, get_company_by_id, insert_contradiction
from shared.kafka_client import publish, consume
from shared.llm import ensure_model_available

from .agent import evaluate_contradiction_pair

logger = logging.getLogger(__name__)

# Candidate retrieval (vector)
SIMILARITY_THRESHOLD = 0.5
MAX_CANDIDATES = 20


def _claim_row(row) -> dict:
    return {
        "id": row["id"],
        "claim_text": row["claim_text"],
        "claim_type": row.get("claim_type"),
        "topic": row.get("topic"),
        "embedding": row.get("embedding"),
        "claim_date": row.get("claim_date"),
        "source_section": row.get("source_section"),
        "entities": row.get("entities"),
    }


async def detect_contradictions_for_filing(filing_id: int, company_id: int):
    """Find contradictions between new claims and historical claims (agent + tools)."""
    pool = await get_pool()
    company = await get_company_by_id(company_id)
    if not company:
        logger.error(f"Company id {company_id} not found; skip filing {filing_id}")
        return 0

    new_claims = await pool.fetch(
        """SELECT id, claim_text, claim_type, topic, embedding, claim_date, source_section, entities
           FROM claims
           WHERE filing_id = $1 AND embedding IS NOT NULL""",
        filing_id,
    )

    if not new_claims:
        logger.info(f"No claims found for filing {filing_id}")
        return 0

    logger.info(f"Checking {len(new_claims)} claims for contradictions")
    contradiction_count = 0

    for claim in new_claims:
        embedding_str = str(claim["embedding"])
        candidates = await get_similar_claims(
            embedding_str=embedding_str,
            company_id=company_id,
            exclude_filing_id=filing_id,
            limit=MAX_CANDIDATES,
            threshold=SIMILARITY_THRESHOLD,
        )

        if not candidates:
            continue

        claim_d = _claim_row(claim)

        for candidate in candidates:
            cand_d = _claim_row(candidate)
            outcome = await evaluate_contradiction_pair(
                claim_d,
                cand_d,
                company,
                float(candidate["similarity"]),
            )
            if not outcome:
                continue

            contra_id = await insert_contradiction(
                claim_a_id=outcome["claim_a_id"],
                claim_b_id=outcome["claim_b_id"],
                company_id=company_id,
                similarity_score=outcome["similarity_score"],
                nli_score=outcome["nli_score"],
                severity=outcome["severity"],
                time_gap_days=outcome["time_gap_days"],
                explanation=outcome["explanation"],
                agent_reasoning=outcome["agent_reasoning"],
            )

            await publish("contradiction.found", {
                "contradiction_id": contra_id,
                "company_id": company_id,
                "company_ticker": company["ticker"] if company else None,
                "severity": outcome["severity"],
                "claim_a_id": outcome["claim_a_id"],
                "claim_b_id": outcome["claim_b_id"],
            })

            contradiction_count += 1
            logger.info(
                f"  Contradiction stored (severity={outcome['severity']}, "
                f"NLI={outcome['nli_score']:.2f}): "
                f"claims {outcome['claim_a_id']} vs {outcome['claim_b_id']}"
            )

    logger.info(f"Found {contradiction_count} contradictions for filing {filing_id}")
    return contradiction_count


async def run_consumer():
    """Kafka consumer processing claims.extracted events."""
    await ensure_model_available()

    async def handle(data: dict) -> None:
        filing_id = data["filing_id"]
        company_id = data["company_id"]
        try:
            count = await detect_contradictions_for_filing(filing_id, company_id)
            logger.info(f"Processed filing {filing_id}: {count} contradictions")
        except Exception as e:
            logger.error(f"Failed to detect contradictions for filing {filing_id}: {e}")
            raise

    await consume("claims.extracted", "contradiction-detectors", handle)

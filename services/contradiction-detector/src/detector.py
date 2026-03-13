"""Main contradiction detection pipeline."""

import logging
import sys

sys.path.insert(0, "/app")

from shared.db import get_pool, get_similar_claims, insert_contradiction
from shared.redis_client import publish_event, create_consumer_group, consume_events
from .nli_scorer import score_pairs, classify_severity

logger = logging.getLogger(__name__)

# Thresholds
SIMILARITY_THRESHOLD = 0.5
NLI_CONTRADICTION_THRESHOLD = 0.6
MAX_CANDIDATES = 20


async def detect_contradictions_for_filing(filing_id: int, company_id: int):
    """Find contradictions between new claims and historical claims."""
    pool = await get_pool()

    # Get new claims from this filing
    new_claims = await pool.fetch(
        """SELECT id, claim_text, claim_type, topic, embedding, claim_date
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
        # Get similar historical claims via pgvector
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

        # Build pairs for NLI scoring
        pairs = [(claim["claim_text"], c["claim_text"]) for c in candidates]
        nli_results = score_pairs(pairs)

        # Check for contradictions
        for i, (candidate, nli_result) in enumerate(zip(candidates, nli_results)):
            if nli_result["contradiction"] >= NLI_CONTRADICTION_THRESHOLD:
                similarity = candidate["similarity"]

                # Calculate time gap
                time_gap = None
                if claim["claim_date"] and candidate["claim_date"]:
                    time_gap = abs((claim["claim_date"] - candidate["claim_date"]).days)

                severity = classify_severity(
                    nli_result["contradiction"],
                    similarity,
                    time_gap,
                )

                # Generate explanation
                explanation = (
                    f"Potential contradiction detected (NLI score: {nli_result['contradiction']:.2f}, "
                    f"similarity: {similarity:.2f}). "
                    f"Claim A (dated {candidate['claim_date']}): \"{candidate['claim_text'][:200]}\" "
                    f"vs Claim B (dated {claim['claim_date']}): \"{claim['claim_text'][:200]}\""
                )

                # Determine which claim is older (claim_a) vs newer (claim_b)
                if claim["claim_date"] and candidate["claim_date"]:
                    if claim["claim_date"] >= candidate["claim_date"]:
                        claim_a_id, claim_b_id = candidate["id"], claim["id"]
                    else:
                        claim_a_id, claim_b_id = claim["id"], candidate["id"]
                else:
                    claim_a_id, claim_b_id = candidate["id"], claim["id"]

                contra_id = await insert_contradiction(
                    claim_a_id=claim_a_id,
                    claim_b_id=claim_b_id,
                    company_id=company_id,
                    similarity_score=similarity,
                    nli_score=nli_result["contradiction"],
                    severity=severity,
                    time_gap_days=time_gap,
                    explanation=explanation,
                )

                # Publish event
                await publish_event("contradiction.found", {
                    "contradiction_id": contra_id,
                    "company_id": company_id,
                    "severity": severity,
                    "claim_a_id": claim_a_id,
                    "claim_b_id": claim_b_id,
                })

                contradiction_count += 1
                logger.info(
                    f"  Contradiction found (severity={severity}, "
                    f"NLI={nli_result['contradiction']:.2f}): "
                    f"claims {claim_a_id} vs {claim_b_id}"
                )

    logger.info(f"Found {contradiction_count} contradictions for filing {filing_id}")
    return contradiction_count


async def run_consumer():
    """Run as a Redis Streams consumer processing claim extraction events."""
    stream = "claims.extracted"
    group = "contradiction-detectors"
    consumer = "detector-1"

    await create_consumer_group(stream, group)
    logger.info(f"Listening on stream '{stream}' as {group}/{consumer}")

    while True:
        try:
            events = await consume_events(stream, group, consumer, count=5)
            for msg_id, data in events:
                filing_id = data["filing_id"]
                company_id = data["company_id"]
                try:
                    count = await detect_contradictions_for_filing(filing_id, company_id)
                    logger.info(f"Processed filing {filing_id}: {count} contradictions")
                except Exception as e:
                    logger.error(f"Failed to detect contradictions for filing {filing_id}: {e}")
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            import asyncio
            await asyncio.sleep(5)

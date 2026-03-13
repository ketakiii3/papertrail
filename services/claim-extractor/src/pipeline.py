"""Main claim extraction pipeline orchestrator."""

import json
import logging
import sys

sys.path.insert(0, "/app")

from shared.db import get_pool, get_filing, mark_filing_processed, insert_claims_batch
from shared.redis_client import publish_event, create_consumer_group, consume_events

from .splitter import (
    split_into_sections, extract_sentences, is_claim_sentence,
    classify_claim_type, classify_topic,
)
from .claim_classifier import get_classifier
from .entity_extractor import extract_entities, extract_temporal_ref
from .embedder import embed_texts

logger = logging.getLogger(__name__)


async def process_filing(filing_id: int, company_id: int):
    """Process a single filing through the full NLP pipeline."""
    filing = await get_filing(filing_id)
    if not filing:
        logger.error(f"Filing {filing_id} not found")
        return 0

    if filing["processed"]:
        logger.info(f"Filing {filing_id} already processed, skipping")
        return 0

    raw_text = filing.get("raw_text", "")
    if not raw_text or len(raw_text) < 100:
        logger.warning(f"Filing {filing_id} has no text")
        return 0

    form_type = filing["form_type"]
    filed_at = filing["filed_at"]

    logger.info(f"Processing filing {filing_id} ({form_type})")

    # Step 1: Split into sections
    sections = split_into_sections(raw_text, form_type)
    logger.info(f"  Found {len(sections)} sections")

    # Step 2: Extract sentences and filter for claims
    all_claims = []
    for section in sections:
        sentences = extract_sentences(section["text"])
        for sentence in sentences:
            if is_claim_sentence(sentence):
                all_claims.append({
                    "text": sentence,
                    "section": section["section"],
                })

    logger.info(f"  Extracted {len(all_claims)} candidate claims")

    if not all_claims:
        await mark_filing_processed(filing_id)
        return 0

    # Cap at 200 claims per filing for MVP
    all_claims = all_claims[:200]

    # Step 3: Classify sentiment with FinBERT
    claim_texts = [c["text"] for c in all_claims]
    classifier = get_classifier()
    sentiments = classifier.classify_sentiment(claim_texts)

    # Step 4: Extract entities and classify
    for i, claim in enumerate(all_claims):
        claim["sentiment"] = sentiments[i]["label"]
        claim["confidence"] = sentiments[i]["confidence"]
        claim["claim_type"] = classify_claim_type(claim["text"])
        claim["topic"] = classify_topic(claim["text"])
        claim["entities"] = extract_entities(claim["text"])
        claim["temporal_ref"] = extract_temporal_ref(claim["text"])

    # Step 5: Generate embeddings
    embeddings = embed_texts(claim_texts)

    # Step 6: Prepare for DB insertion
    db_claims = []
    for i, claim in enumerate(all_claims):
        embedding_str = "[" + ",".join(str(x) for x in embeddings[i]) + "]"
        db_claims.append({
            "filing_id": filing_id,
            "company_id": company_id,
            "speaker": None,  # Not available from filings, only transcripts
            "claim_text": claim["text"],
            "claim_type": claim["claim_type"],
            "topic": claim["topic"],
            "sentiment": claim["sentiment"],
            "confidence": claim["confidence"],
            "entities": json.dumps(claim["entities"]),
            "temporal_ref": claim.get("temporal_ref"),
            "source_section": claim["section"],
            "embedding": embedding_str,
            "claim_date": filed_at,
        })

    # Step 7: Insert into DB
    await insert_claims_batch(db_claims)
    await mark_filing_processed(filing_id)

    # Step 8: Publish event for contradiction detection
    await publish_event("claims.extracted", {
        "filing_id": filing_id,
        "company_id": company_id,
        "claim_count": len(db_claims),
    })

    logger.info(f"  Stored {len(db_claims)} claims for filing {filing_id}")
    return len(db_claims)


async def run_consumer():
    """Run as a Redis Streams consumer processing filing events."""
    stream = "filing.new"
    group = "claim-extractors"
    consumer = "extractor-1"

    await create_consumer_group(stream, group)
    logger.info(f"Listening on stream '{stream}' as {group}/{consumer}")

    while True:
        try:
            events = await consume_events(stream, group, consumer, count=5)
            for msg_id, data in events:
                filing_id = data["filing_id"]
                company_id = data["company_id"]
                try:
                    count = await process_filing(filing_id, company_id)
                    logger.info(f"Processed filing {filing_id}: {count} claims")
                except Exception as e:
                    logger.error(f"Failed to process filing {filing_id}: {e}")
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            import asyncio
            await asyncio.sleep(5)

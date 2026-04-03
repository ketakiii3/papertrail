"""Zero-shot topic classification using BART-MNLI."""

import logging
from transformers import pipeline

logger = logging.getLogger(__name__)

_classifier = None

CANDIDATE_LABELS = [
    "revenue and sales",
    "profitability and earnings",
    "workforce and restructuring",
    "business growth and expansion",
    "mergers and acquisitions",
    "regulatory and legal compliance",
    "product development and innovation",
    "capital allocation and dividends",
    "supply chain and logistics",
    "macroeconomic conditions",
]

# Map model labels back to short topic keys
LABEL_TO_TOPIC = {
    "revenue and sales": "revenue",
    "profitability and earnings": "profitability",
    "workforce and restructuring": "workforce",
    "business growth and expansion": "growth",
    "mergers and acquisitions": "m&a",
    "regulatory and legal compliance": "regulatory",
    "product development and innovation": "product",
    "capital allocation and dividends": "capital",
    "supply chain and logistics": "supply_chain",
    "macroeconomic conditions": "macro",
}


def get_topic_classifier():
    global _classifier
    if _classifier is None:
        logger.info("Loading BART-MNLI zero-shot classification model...")
        _classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=-1,  # CPU; set to 0 for GPU
        )
        logger.info("BART-MNLI model loaded")
    return _classifier


def classify_topics_batch(texts: list[str], threshold: float = 0.3) -> list[str]:
    """Classify topics for a batch of texts using zero-shot classification.

    Args:
        texts: List of claim texts
        threshold: Minimum confidence to assign a topic (below = "general")

    Returns:
        List of topic strings
    """
    if not texts:
        return []

    classifier = get_topic_classifier()
    topics = []

    # Process in batches to manage memory
    batch_size = 8
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        results = classifier(
            batch,
            candidate_labels=CANDIDATE_LABELS,
            multi_label=False,
        )

        # Handle single result (not wrapped in list)
        if isinstance(results, dict):
            results = [results]

        for result in results:
            top_label = result["labels"][0]
            top_score = result["scores"][0]

            if top_score >= threshold:
                topics.append(LABEL_TO_TOPIC.get(top_label, "general"))
            else:
                topics.append("general")

    return topics

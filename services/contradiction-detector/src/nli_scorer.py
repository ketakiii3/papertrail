"""Natural Language Inference scoring for contradiction detection."""

import logging

import numpy as np
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

_model = None

# NLI labels from cross-encoder/nli-deberta-v3-base
LABELS = ["contradiction", "entailment", "neutral"]


def get_model() -> CrossEncoder:
    global _model
    if _model is None:
        logger.info("Loading NLI cross-encoder model...")
        _model = CrossEncoder("cross-encoder/nli-deberta-v3-base")
        logger.info("NLI model loaded")
    return _model


def score_pairs(pairs: list[tuple[str, str]]) -> list[dict]:
    """Score claim pairs for contradiction/entailment/neutral.

    Args:
        pairs: List of (claim_a_text, claim_b_text) tuples

    Returns:
        List of dicts with scores for each label and predicted label
    """
    if not pairs:
        return []

    model = get_model()
    scores = model.predict(pairs)

    results = []
    for score_row in scores:
        # Softmax
        exp_scores = np.exp(score_row - np.max(score_row))
        probs = exp_scores / exp_scores.sum()

        result = {
            "contradiction": float(probs[0]),
            "entailment": float(probs[1]),
            "neutral": float(probs[2]),
            "predicted_label": LABELS[np.argmax(probs)],
        }
        results.append(result)

    return results


def classify_severity(nli_score: float, similarity: float, time_gap_days: int = None) -> str:
    """Classify contradiction severity based on multiple signals."""
    score = nli_score * 0.5 + similarity * 0.3

    # Shorter time gaps between contradicting claims are more severe
    if time_gap_days is not None:
        if time_gap_days < 30:
            score += 0.2
        elif time_gap_days < 90:
            score += 0.1

    if score >= 0.85:
        return "critical"
    elif score >= 0.7:
        return "high"
    elif score >= 0.5:
        return "medium"
    else:
        return "low"

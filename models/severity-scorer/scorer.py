"""Contradiction severity scoring model.

Uses a weighted combination of signals to produce a severity score:
- NLI contradiction probability
- Semantic similarity (topic overlap)
- Time gap between claims
- Claim specificity (presence of numbers, dates, named entities)
- Topic materiality (some topics are more material than others)
- Insider trading context (sells between claims = more suspicious)
"""

import re
from dataclasses import dataclass


@dataclass
class SeverityInput:
    nli_score: float             # 0-1, contradiction probability
    similarity: float            # 0-1, cosine similarity
    time_gap_days: int | None    # Days between claims
    claim_a_text: str
    claim_b_text: str
    topic: str | None
    insider_sells_between: int = 0  # Number of insider sells between claim dates
    insider_sell_value: float = 0   # Total value of insider sells


# Topics ranked by materiality impact
TOPIC_MATERIALITY = {
    "workforce": 0.9,      # Restructuring, layoffs = highly material
    "m&a": 0.9,            # Mergers, acquisitions
    "revenue": 0.85,       # Revenue guidance changes
    "profitability": 0.85,
    "regulatory": 0.8,     # Legal/regulatory issues
    "capital": 0.75,       # Capital allocation changes
    "growth": 0.7,
    "product": 0.65,
    "supply_chain": 0.6,
    "macro": 0.5,
    "general": 0.4,
}


def compute_specificity(text: str) -> float:
    """Score how specific/quantitative a claim is. More specific = higher severity if contradicted."""
    score = 0.0

    # Numbers and percentages
    if re.search(r"\d+%|\d+\s*percent", text, re.IGNORECASE):
        score += 0.25
    if re.search(r"\$[\d,]+", text):
        score += 0.25

    # Absolute negations or affirmations
    if re.search(r"\b(no\s+plans?|will\s+not|do\s+not|never)\b", text, re.IGNORECASE):
        score += 0.3
    if re.search(r"\b(committed|guarantee|certain|definite)\b", text, re.IGNORECASE):
        score += 0.2

    # Temporal specificity
    if re.search(r"\b(next\s+quarter|fy\d{2}|q[1-4]|by\s+\w+\s+\d{4})\b", text, re.IGNORECASE):
        score += 0.15

    # Named entities (companies, products)
    if re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text):
        score += 0.1

    return min(score, 1.0)


def score_severity(inp: SeverityInput) -> dict:
    """Compute severity score and classification.

    Returns:
        {
            "score": float (0-1),
            "severity": "low" | "medium" | "high" | "critical",
            "factors": dict of contributing factors
        }
    """
    factors = {}

    # Factor 1: NLI contradiction strength (weight: 0.30)
    factors["nli_strength"] = inp.nli_score
    nli_component = inp.nli_score * 0.30

    # Factor 2: Topic overlap / relevance (weight: 0.15)
    factors["topic_overlap"] = inp.similarity
    similarity_component = inp.similarity * 0.15

    # Factor 3: Time gap - shorter = more severe (weight: 0.15)
    if inp.time_gap_days is not None:
        if inp.time_gap_days <= 14:
            time_score = 1.0
        elif inp.time_gap_days <= 30:
            time_score = 0.9
        elif inp.time_gap_days <= 90:
            time_score = 0.7
        elif inp.time_gap_days <= 180:
            time_score = 0.5
        else:
            time_score = 0.3
    else:
        time_score = 0.5
    factors["time_proximity"] = time_score
    time_component = time_score * 0.15

    # Factor 4: Claim specificity (weight: 0.15)
    spec_a = compute_specificity(inp.claim_a_text)
    spec_b = compute_specificity(inp.claim_b_text)
    specificity = max(spec_a, spec_b)
    factors["specificity"] = specificity
    specificity_component = specificity * 0.15

    # Factor 5: Topic materiality (weight: 0.10)
    materiality = TOPIC_MATERIALITY.get(inp.topic or "general", 0.4)
    factors["topic_materiality"] = materiality
    materiality_component = materiality * 0.10

    # Factor 6: Insider trading context (weight: 0.15)
    if inp.insider_sells_between > 0:
        insider_score = min(1.0, 0.5 + inp.insider_sells_between * 0.1
                           + min(inp.insider_sell_value / 1_000_000, 0.5))
    else:
        insider_score = 0.0
    factors["insider_suspicion"] = insider_score
    insider_component = insider_score * 0.15

    # Total score
    total = (nli_component + similarity_component + time_component
             + specificity_component + materiality_component + insider_component)

    # Classification
    if total >= 0.75:
        severity = "critical"
    elif total >= 0.55:
        severity = "high"
    elif total >= 0.35:
        severity = "medium"
    else:
        severity = "low"

    return {
        "score": round(total, 4),
        "severity": severity,
        "factors": {k: round(v, 4) for k, v in factors.items()},
    }

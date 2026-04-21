"""Agent tools for contradiction detection (5.2) — callable units with structured outputs."""

from __future__ import annotations

import json
import logging
from typing import Any

from .nli_scorer import classify_severity, score_pairs

logger = logging.getLogger(__name__)


def _entities_payload(raw: Any) -> dict | list | None:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None
    return None


def _topic_overlap(topic_a: str | None, topic_b: str | None) -> bool:
    if not topic_a or not topic_b:
        return False
    return topic_a.strip().lower() == topic_b.strip().lower()


def _shared_entity_hits(entities_a: Any, entities_b: Any) -> list[str]:
    """Rough overlap: same string values appearing in both entity dicts."""
    ea = _entities_payload(entities_a)
    eb = _entities_payload(entities_b)
    if not isinstance(ea, dict) or not isinstance(eb, dict):
        return []
    vals_a: set[str] = set()
    vals_b: set[str] = set()
    for d, acc in ((ea, vals_a), (eb, vals_b)):
        for v in d.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and len(x) > 1:
                        acc.add(x.lower())
            elif isinstance(v, str) and len(v) > 1:
                acc.add(v.lower())
    shared = sorted(vals_a & vals_b)
    return shared[:20]


def semantic_compare(
    claim_a: dict,
    claim_b: dict,
    vector_similarity: float,
) -> dict[str, Any]:
    """Tool: semantic similarity (from pgvector), topic overlap, entity overlap, short NL summary."""
    ta, tb = claim_a.get("topic"), claim_b.get("topic")
    overlap_topics = _topic_overlap(
        ta if isinstance(ta, str) else None,
        tb if isinstance(tb, str) else None,
    )
    shared = _shared_entity_hits(claim_a.get("entities"), claim_b.get("entities"))
    summary = (
        f"Similarity {vector_similarity:.2f}; topics_match={overlap_topics}; "
        f"shared_entity_strings={len(shared)}"
    )
    return {
        "cosine_similarity": float(vector_similarity),
        "topic_overlap": overlap_topics,
        "shared_entities": shared,
        "comparison_summary": summary,
    }


def check_negation(claim_a_text: str, claim_b_text: str) -> dict[str, Any]:
    """Tool: NLI cross-encoder — entailment / neutral / contradiction probabilities."""
    results = score_pairs([(claim_a_text, claim_b_text)])
    if not results:
        return {
            "contradiction": 0.0,
            "entailment": 0.0,
            "neutral": 0.0,
            "predicted_label": "neutral",
        }
    r = results[0]
    return {
        "contradiction": r["contradiction"],
        "entailment": r["entailment"],
        "neutral": r["neutral"],
        "predicted_label": r["predicted_label"],
    }


def temporal_check(
    claim_a: dict,
    claim_b: dict,
) -> dict[str, Any]:
    """Tool: ordering and gap. For a forward-looking contradiction, the later-dated claim is claim_b."""
    da = claim_a.get("claim_date")
    db = claim_b.get("claim_date")
    if not da or not db:
        return {
            "time_gap_days": None,
            "b_after_a": None,
            "valid_order_for_analysis": True,
            "note": "missing one or both claim dates",
        }
    gap = abs((db - da).days)
    b_after_a = db > da
    return {
        "time_gap_days": gap,
        "b_after_a": b_after_a,
        "valid_order_for_analysis": True,
        "note": "claim_b is newer than claim_a" if b_after_a else "claim_b is not strictly after claim_a (still analyzed)",
    }


def severity_score(
    nli_contradiction: float,
    similarity: float,
    time_gap_days: int | None,
    insider_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Tool: map signals + optional insider Form 4 context into a severity bucket."""
    base = classify_severity(nli_contradiction, similarity, time_gap_days)
    insider_flag = False
    order = ["low", "medium", "high", "critical"]
    if insider_context and insider_context.get("large_insider_sales"):
        insider_flag = True
        idx = order.index(base) if base in order else 1
        base = order[min(idx + 1, len(order) - 1)]
    return {
        "severity": base,
        "insider_escalation": insider_flag,
        "factors": {
            "nli_contradiction": nli_contradiction,
            "similarity": similarity,
            "time_gap_days": time_gap_days,
        },
    }


def summarize_insider_rows(rows: list[dict]) -> dict[str, Any]:
    """Derive flags from raw insider_transactions rows."""
    if not rows:
        return {
            "transaction_count": 0,
            "sell_count": 0,
            "total_sell_value": 0.0,
            "large_insider_sales": False,
            "summary": "No insider transactions in window",
        }
    sells = [
        r
        for r in rows
        if str(r.get("transaction_type", "")).lower() in ("sell", "s", "sale")
    ]
    total = 0.0
    for r in sells:
        v = r.get("total_value")
        if v is not None:
            total += float(v)
    large = total >= 500_000 or len(sells) >= 3
    return {
        "transaction_count": len(rows),
        "sell_count": len(sells),
        "total_sell_value": round(total, 2),
        "large_insider_sales": large,
        "summary": f"{len(sells)} sells, ~${total:,.0f} notional in window",
    }

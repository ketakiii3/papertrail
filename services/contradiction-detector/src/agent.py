"""Contradiction detection agent (5.2): orchestrates tools with visible log lines."""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.db import get_insider_transactions_between
from shared.llm import generate_reasoning

from .agent_tools import (
    check_negation,
    semantic_compare,
    severity_score,
    summarize_insider_rows,
    temporal_check,
)

logger = logging.getLogger(__name__)

NLI_CONTRADICTION_THRESHOLD = 0.6


def _short(obj: Any, limit: int = 400) -> str:
    s = json.dumps(obj, default=str) if not isinstance(obj, str) else obj
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _log_tool(name: str, result: dict) -> None:
    logger.info("[AGENT_TOOL] %s -> %s", name, _short(result))


def _log_agent(event: str, **kwargs: Any) -> None:
    logger.info("[AGENT] %s %s", event, _short(kwargs))


def _order_claim_pair(
    claim_new: dict,
    candidate: dict,
) -> tuple[dict, dict, int, int]:
    """Older claim = A, newer = B (for temporal + PRD narrative)."""
    dn, dc = claim_new.get("claim_date"), candidate.get("claim_date")
    if dn and dc:
        if dn >= dc:
            return candidate, claim_new, candidate["id"], claim_new["id"]
        return claim_new, candidate, claim_new["id"], candidate["id"]
    return candidate, claim_new, candidate["id"], claim_new["id"]


async def evaluate_contradiction_pair(
    claim_new: dict,
    candidate: dict,
    company: dict,
    vector_similarity: float,
) -> dict | None:
    """
    Run the tool pipeline with logging. Returns a dict ready for insert_contradiction,
    or None if this pair is not treated as a contradiction.
    """
    ca, cb, id_a, id_b = _order_claim_pair(claim_new, candidate)
    _log_agent(
        "session_start",
        pair=f"{id_a}_vs_{id_b}",
        ticker=company.get("ticker"),
        vector_similarity=round(vector_similarity, 4),
    )

    # 1) Semantic / overlap (uses pgvector similarity + entity/topic heuristics)
    sem = semantic_compare(ca, cb, vector_similarity)
    _log_tool("semantic_compare", sem)

    # 2) NLI
    nli = check_negation(ca["claim_text"], cb["claim_text"])
    _log_tool("check_negation", nli)

    if nli["contradiction"] < NLI_CONTRADICTION_THRESHOLD:
        _log_agent("decision", is_contradiction=False, reason="nli_below_threshold")
        return None

    # 3) Temporal
    tmp = temporal_check(ca, cb)
    _log_tool("temporal_check", tmp)

    time_gap = tmp.get("time_gap_days")
    if isinstance(time_gap, (int, float)):
        time_gap = int(time_gap)

    # 4) Insider context (only after NLI says contradiction — saves DB work)
    insider_summary: dict[str, Any] = {
        "transaction_count": 0,
        "sell_count": 0,
        "total_sell_value": 0.0,
        "large_insider_sales": False,
        "summary": "skipped",
    }
    da, db = ca.get("claim_date"), cb.get("claim_date")
    if da and db:
        lo, hi = (da, db) if da <= db else (db, da)
        rows = await get_insider_transactions_between(company["id"], lo, hi)
        insider_summary = summarize_insider_rows(rows)
        _log_tool(
            "get_insider_context",
            {
                "window": f"{lo} .. {hi}",
                **insider_summary,
            },
        )
    else:
        _log_agent("tool_skip", tool="get_insider_context", reason="missing_claim_dates")

    # 5) Severity
    sev = severity_score(
        nli["contradiction"],
        float(sem["cosine_similarity"]),
        time_gap if isinstance(time_gap, int) else None,
        insider_summary,
    )
    _log_tool("severity_score", sev)

    explanation = (
        f"Agent pipeline: NLI contradiction={nli['contradiction']:.2f}, "
        f"similarity={sem['cosine_similarity']:.2f}, severity={sev['severity']}. "
        f"{sem['comparison_summary']}. Insider: {insider_summary.get('summary', '')}"
    )

    tool_digest = (
        f"semantic_compare: {sem['comparison_summary']}\n"
        f"check_negation: label={nli['predicted_label']} p_contra={nli['contradiction']:.3f}\n"
        f"temporal_check: gap={tmp.get('time_gap_days')} b_after_a={tmp.get('b_after_a')}\n"
        f"get_insider_context: {insider_summary.get('summary')}\n"
        f"severity_score: {sev['severity']} insider_esc={sev.get('insider_escalation')}"
    )

    agent_reasoning = await generate_reasoning(
        company_name=company.get("name") or "Unknown",
        ticker=company.get("ticker") or "???",
        claim_a=ca["claim_text"],
        claim_b=cb["claim_text"],
        date_a=str(ca["claim_date"]) if ca.get("claim_date") else None,
        date_b=str(cb["claim_date"]) if cb.get("claim_date") else None,
        section_a=ca.get("source_section"),
        section_b=cb.get("source_section"),
        severity=sev["severity"],
        nli_score=nli["contradiction"],
        time_gap=time_gap if isinstance(time_gap, int) else None,
        tool_digest=tool_digest,
    )

    _log_agent(
        "decision",
        is_contradiction=True,
        severity=sev["severity"],
        claim_a_id=id_a,
        claim_b_id=id_b,
    )

    return {
        "claim_a_id": id_a,
        "claim_b_id": id_b,
        "similarity_score": float(sem["cosine_similarity"]),
        "nli_score": nli["contradiction"],
        "severity": sev["severity"],
        "time_gap_days": time_gap if isinstance(time_gap, int) else None,
        "explanation": explanation,
        "agent_reasoning": agent_reasoning,
    }

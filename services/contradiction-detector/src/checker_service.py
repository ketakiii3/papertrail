"""Runs the checker agent on stored contradictions: load, check, persist, publish.

Consumes `contradiction.found` in its own consumer group (`contradiction-checkers`),
so slow local inference never holds up detection. Idempotent: a pair already
checked with the same model + prompt version is skipped, so redelivery is free.
"""

from __future__ import annotations

import json
import logging

from shared.config import settings
from shared.db import get_pool
from shared.kafka_client import consume, publish

from .checker import PROMPT_VERSION, PROVIDER, PostgresCheckerData, run_checker

logger = logging.getLogger(__name__)


async def load_pair(pool, contradiction_id: int) -> dict | None:
    r = await pool.fetchrow(
        """SELECT con.id, con.company_id, con.similarity_score, con.nli_contradiction_score,
                  con.severity, con.time_gap_days, co.ticker, co.name AS company_name,
                  ca.id AS a_id, ca.claim_text AS a_text, ca.claim_date AS a_date,
                  ca.source_section AS a_section, fa.form_type AS a_form,
                  cb.id AS b_id, cb.claim_text AS b_text, cb.claim_date AS b_date,
                  cb.source_section AS b_section, fb.form_type AS b_form
           FROM contradictions con
           JOIN companies co ON co.id = con.company_id
           JOIN claims ca ON ca.id = con.claim_a_id JOIN filings fa ON fa.id = ca.filing_id
           JOIN claims cb ON cb.id = con.claim_b_id JOIN filings fb ON fb.id = cb.filing_id
           WHERE con.id = $1""",
        contradiction_id,
    )
    if not r:
        return None
    side = lambda p: {"id": r[f"{p}_id"], "text": r[f"{p}_text"], "date": r[f"{p}_date"],  # noqa: E731
                      "section": r[f"{p}_section"], "form": r[f"{p}_form"]}
    return {
        "contradiction_id": r["id"], "company_id": r["company_id"], "ticker": r["ticker"],
        "company_name": r["company_name"], "a": side("a"), "b": side("b"),
        "nli": float(r["nli_contradiction_score"]), "similarity": float(r["similarity_score"]),
        "gap": r["time_gap_days"], "severity": r["severity"],
    }


async def already_checked(pool, contradiction_id: int, model: str) -> bool:
    return await pool.fetchval(
        """SELECT EXISTS (SELECT 1 FROM agent_runs
                          WHERE contradiction_id = $1 AND model = $2 AND prompt_version = $3
                            AND stop_reason <> 'error')""",
        contradiction_id, model, PROMPT_VERSION,
    )


async def save_run(pool, contradiction_id: int, model: str, run: dict) -> int | None:
    """Store the run; copy a verdict onto the contradiction. None if a concurrent run won."""
    async with pool.acquire() as conn, conn.transaction():
        run_id = await conn.fetchval(
            """INSERT INTO agent_runs (contradiction_id, provider, model, prompt_version, trace, verdict,
                                       tool_calls, tokens_in, tokens_out, latency_ms, stop_reason, error)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11, $12)
               ON CONFLICT (contradiction_id, model, prompt_version) WHERE stop_reason <> 'error'
               DO NOTHING
               RETURNING id""",
            contradiction_id, PROVIDER, model, PROMPT_VERSION,
            json.dumps(run["trace"], default=str),
            json.dumps(run["verdict"]) if run["verdict"] else None,
            run["tool_calls"], run["tokens_in"], run["tokens_out"], run["latency_ms"],
            run["stop_reason"], run["error"],
        )
        if run_id and run["verdict"]:
            v = run["verdict"]
            # The rationale replaces the old narrative; rules severity is kept for comparison.
            await conn.execute(
                """UPDATE contradictions
                   SET verdict = $2, agent_confidence = $3, agent_run_id = $4, agent_reasoning = $5
                   WHERE id = $1""",
                contradiction_id, v["verdict"], v["confidence"], run_id, v["rationale"],
            )
    return run_id


async def check_contradiction(contradiction_id: int, model=None, data=None) -> dict | None:
    """Check one stored pair. Returns the run, or None if skipped."""
    pool = await get_pool()
    model_name = settings.CHECKER_MODEL if model is None else getattr(model, "model", type(model).__name__)
    if await already_checked(pool, contradiction_id, model_name):
        logger.info("[AGENT] contradiction %s already checked by %s/%s", contradiction_id, model_name, PROMPT_VERSION)
        return None
    pair = await load_pair(pool, contradiction_id)
    if pair is None:
        logger.warning("[AGENT] contradiction %s not found", contradiction_id)
        return None
    logger.info("[AGENT] checking contradiction %s (%s) with %s", contradiction_id, pair["ticker"], model_name)
    run = await run_checker(pair, data or PostgresCheckerData(pool), model)
    run_id = await save_run(pool, contradiction_id, model_name, run)
    if run_id and run["verdict"]:
        v = run["verdict"]
        logger.info("[AGENT] decision contradiction=%s verdict=%s confidence=%.2f tool_calls=%s %sms",
                    contradiction_id, v["verdict"], v["confidence"], run["tool_calls"], run["latency_ms"])
        await publish("contradiction.verified", {
            "contradiction_id": contradiction_id,
            "company_id": pair["company_id"],
            "company_ticker": pair["ticker"],
            "verdict": v["verdict"],
            "agent_confidence": v["confidence"],
            "agent_run_id": run_id,
        })
    return {**run, "agent_run_id": run_id}


async def run_consumer() -> None:
    async def handle(data: dict) -> None:
        if not settings.CHECKER_ENABLED:
            return
        await check_contradiction(data["contradiction_id"])

    await consume("contradiction.found", "contradiction-checkers", handle)

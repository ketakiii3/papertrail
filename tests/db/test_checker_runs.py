"""T3/T4: a checker run is stored with its trace, its verdict is copied onto the
contradiction, and a redelivered message doesn't run the agent again."""

import json

import asyncpg
import pytest
from langchain_core.messages import AIMessage

import contradiction_detector.checker_service as service
from shared.db import insert_contradiction

pytestmark = pytest.mark.db

VERDICT = {"verdict": "boilerplate", "severity": "low", "confidence": 0.9,
           "rationale": "Both claims are cross-references to other documents.", "evidence": []}


def _model():
    from tests.test_checker import ScriptedModel  # same scripted model as the unit tests
    msgs = [AIMessage(content="", tool_calls=[{"name": "get_claim_context", "args": {"claim_id": 0},
                                               "id": "c0", "type": "tool_call"}]),
            AIMessage(content="", tool_calls=[{"name": "submit_verdict", "args": VERDICT,
                                               "id": "c1", "type": "tool_call"}])]
    return ScriptedModel(messages=iter(msgs))


@pytest.fixture
def published(monkeypatch):
    sent = []

    async def fake_publish(topic, payload):
        sent.append((topic, payload))

    monkeypatch.setattr(service, "publish", fake_publish)
    return sent


async def test_run_is_stored_and_redelivery_skips(seeded, db_url, published):
    a, b, _ = seeded["claim_ids"]
    cid = await insert_contradiction(claim_a_id=a, claim_b_id=b, company_id=seeded["company_id"],
                                     similarity_score=0.6, nli_score=0.8, severity="high")

    run = await service.check_contradiction(cid, model=_model())
    again = await service.check_contradiction(cid, model=_model())

    assert run["stop_reason"] == "verdict" and again is None
    conn = await asyncpg.connect(db_url)
    try:
        con = await conn.fetchrow("SELECT verdict, agent_confidence, agent_run_id, agent_reasoning, severity "
                                  "FROM contradictions WHERE id = $1", cid)
        runs = await conn.fetch("SELECT * FROM agent_runs WHERE contradiction_id = $1", cid)
    finally:
        await conn.close()
    assert len(runs) == 1
    assert (con["verdict"], con["agent_confidence"], con["agent_run_id"]) == ("boilerplate", 0.9, runs[0]["id"])
    assert con["agent_reasoning"].startswith("Both claims")
    assert con["severity"] == "high"  # rules severity kept for comparison
    trace = json.loads(runs[0]["trace"])
    assert [t["tool"] for t in trace] == ["get_claim_context", "submit_verdict"]
    assert runs[0]["tool_calls"] == 1 and runs[0]["prompt_version"] == "checker-v2"
    assert published == [("contradiction.verified", {
        "contradiction_id": cid, "company_id": seeded["company_id"], "company_ticker": "EXMP",
        "verdict": "boilerplate", "agent_confidence": 0.9, "agent_run_id": runs[0]["id"]})]


async def test_failed_run_is_recorded_and_can_be_retried(seeded, db_url, published):
    from tests.test_checker import ScriptedModel

    class Broken(ScriptedModel):
        async def _agenerate(self, *args, **kwargs):
            raise ConnectionError("ollama unreachable")

    a, b, _ = seeded["claim_ids"]
    cid = await insert_contradiction(claim_a_id=a, claim_b_id=b, company_id=seeded["company_id"],
                                     similarity_score=0.6, nli_score=0.8, severity="high")

    failed = await service.check_contradiction(cid, model=Broken(messages=iter([])))
    retried = await service.check_contradiction(cid, model=_model())

    assert failed["stop_reason"] == "error" and retried["stop_reason"] == "verdict"
    conn = await asyncpg.connect(db_url)
    try:
        reasons = [r["stop_reason"] for r in await conn.fetch(
            "SELECT stop_reason FROM agent_runs WHERE contradiction_id = $1 ORDER BY id", cid)]
    finally:
        await conn.close()
    assert reasons == ["error", "verdict"]
    assert published[-1][1]["verdict"] == "boilerplate"

"""F1 + F6: the detector skips known pairs, batches NLI once per claim in
(older, newer) order, and never publishes a pair the insert didn't store."""

from datetime import date

import pytest

import contradiction_detector.agent as agent
import contradiction_detector.detector as detector

COMPANY = {"id": 7, "ticker": "EXMP", "name": "Example Corp"}
NEW_CLAIM = {
    "id": 100, "claim_text": "We have no plans to cut jobs.", "claim_type": "strategy",
    "topic": "workforce", "embedding": "[0.1]", "claim_date": date(2025, 6, 1),
    "source_section": "MD&A", "entities": None,
}


def _candidate(cid: int, text: str, d: date) -> dict:
    return {"id": cid, "claim_text": text, "claim_type": "factual", "topic": "workforce",
            "embedding": None, "claim_date": d, "source_section": "Item 1A",
            "entities": None, "similarity": 0.8, "filing_id": 1, "sentiment": None}


def _nli(p: float) -> dict:
    return {"contradiction": p, "entailment": 0.0, "neutral": 1 - p,
            "predicted_label": "contradiction" if p > 0.5 else "neutral"}


class _Pool:
    async def fetch(self, *_args):
        return [NEW_CLAIM]


@pytest.fixture
def wired(monkeypatch):
    calls = {"score_pairs": [], "inserted": [], "published": []}
    candidates = [
        _candidate(1, "We cut 2,000 jobs.", date(2025, 1, 1)),   # older -> becomes A
        _candidate(2, "Already-stored pair.", date(2025, 2, 1)),
        _candidate(3, "Hiring continues.", date(2025, 9, 1)),    # newer -> claim 100 becomes A
    ]

    async def get_pool():
        return _Pool()

    async def get_company_by_id(_cid):
        return COMPANY

    async def get_similar_claims(**_kw):
        return candidates

    async def existing_partners(claim_id, other_ids):
        assert claim_id == 100 and other_ids == [1, 2, 3]
        return {2}

    def score_pairs(pairs):
        calls["score_pairs"].append(pairs)
        return [_nli(0.9), _nli(0.1)]

    async def insert_contradiction(**kw):
        calls["inserted"].append(kw)
        return None if kw["claim_a_id"] == 1 else 555  # pretend (1,100) was stored concurrently

    async def publish(topic, payload):
        calls["published"].append((topic, payload))

    async def no_trades(*_a):
        return []

    async def no_reasoning(**_kw):
        return None

    monkeypatch.setattr(detector, "get_pool", get_pool)
    monkeypatch.setattr(detector, "get_company_by_id", get_company_by_id)
    monkeypatch.setattr(detector, "get_similar_claims", get_similar_claims)
    monkeypatch.setattr(detector, "existing_contradiction_partners", existing_partners)
    monkeypatch.setattr(detector, "score_pairs", score_pairs)
    monkeypatch.setattr(detector, "insert_contradiction", insert_contradiction)
    monkeypatch.setattr(detector, "publish", publish)
    monkeypatch.setattr(agent, "get_insider_transactions_between", no_trades)
    monkeypatch.setattr(agent, "generate_reasoning", no_reasoning)
    monkeypatch.setattr(agent, "check_negation", lambda *_a: pytest.fail("NLI recomputed per pair"))
    return calls


async def test_batches_nli_once_in_older_newer_order(wired):
    await detector.detect_contradictions_for_filing(filing_id=9, company_id=7)
    assert wired["score_pairs"] == [[
        ("We cut 2,000 jobs.", "We have no plans to cut jobs."),   # (1 older, 100 newer)
        ("We have no plans to cut jobs.", "Hiring continues."),    # (100 older, 3 newer)
    ]]


async def test_known_pair_skipped_and_noop_insert_not_published(wired):
    count = await detector.detect_contradictions_for_filing(filing_id=9, company_id=7)
    # Only the (1, 100) pair cleared the NLI threshold; its insert was a no-op.
    assert [(k["claim_a_id"], k["claim_b_id"]) for k in wired["inserted"]] == [(1, 100)]
    assert wired["published"] == []
    assert count == 0

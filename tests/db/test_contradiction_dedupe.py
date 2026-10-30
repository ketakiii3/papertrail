"""F1: one contradictions row per unordered claim pair."""

import asyncpg
import pytest

from shared.db import existing_contradiction_partners, insert_contradiction

pytestmark = pytest.mark.db


async def _insert(company_id, a, b):
    return await insert_contradiction(
        claim_a_id=a, claim_b_id=b, company_id=company_id,
        similarity_score=0.8, nli_score=0.9, severity="high",
    )


async def test_same_pair_in_either_order_is_stored_once(seeded, db_url):
    a, b, _ = seeded["claim_ids"]
    first = await _insert(seeded["company_id"], a, b)
    again = await _insert(seeded["company_id"], a, b)
    reversed_ = await _insert(seeded["company_id"], b, a)

    assert isinstance(first, int)
    assert again is None
    assert reversed_ is None
    conn = await asyncpg.connect(db_url)
    try:
        assert await conn.fetchval("SELECT COUNT(*) FROM contradictions") == 1
    finally:
        await conn.close()


async def test_existing_partners_matches_both_orders(seeded):
    a, b, c = seeded["claim_ids"]
    await _insert(seeded["company_id"], a, b)
    await _insert(seeded["company_id"], c, a)

    assert await existing_contradiction_partners(a, [b, c]) == {b, c}
    assert await existing_contradiction_partners(b, [a, c]) == {a}
    assert await existing_contradiction_partners(c, [b]) == set()
    assert await existing_contradiction_partners(c, []) == set()

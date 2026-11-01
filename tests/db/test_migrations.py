"""F0-F2: migrations apply to a database created from the original schema,
remove the duplicates the old code could create, and are no-ops on a fresh
install (init.sql already contains them)."""

from pathlib import Path

import asyncpg
import pytest

from scripts.migrate import migrate

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[2]
V0_SCHEMA = (ROOT / "tests" / "fixtures" / "init_v0.sql").read_text()  # infra/init.sql before migrations existed


async def test_fresh_install_has_nothing_to_apply(make_db):
    url = await make_db((ROOT / "infra" / "init.sql").read_text())
    assert await migrate(url) == []


async def test_legacy_database_is_deduped_and_constrained(make_db):
    url = await make_db(V0_SCHEMA)
    conn = await asyncpg.connect(url)
    try:
        cid = await conn.fetchval("INSERT INTO companies (ticker, name, cik) VALUES ('EXMP','Ex','1') RETURNING id")
        fid = await conn.fetchval(
            "INSERT INTO filings (company_id, accession_number, form_type, filed_at, url) "
            "VALUES ($1, 'acc-1', '10-K', now(), 'u') RETURNING id", cid)
        a = await conn.fetchval("INSERT INTO claims (filing_id, company_id, claim_text) VALUES ($1,$2,'a') RETURNING id", fid, cid)
        b = await conn.fetchval("INSERT INTO claims (filing_id, company_id, claim_text) VALUES ($1,$2,'b') RETURNING id", fid, cid)
        for x, y in ((a, b), (a, b), (b, a)):
            await conn.execute(
                "INSERT INTO contradictions (claim_a_id, claim_b_id, company_id, similarity_score, nli_contradiction_score) "
                "VALUES ($1, $2, $3, 0.8, 0.9)", x, y, cid)
        for _ in range(2):
            await conn.execute(
                "INSERT INTO insider_transactions (company_id, insider_name, transaction_type, shares, price, "
                "transaction_date, filing_date) VALUES ($1, 'Doe Jane', 'sell', 100, 10.00, '2025-01-02', '2025-01-03')",
                cid)
        dup_txn = await conn.fetchval("SELECT MAX(id) FROM insider_transactions")
        seeded_txn = await conn.fetchval(
            "INSERT INTO insider_transactions (company_id, insider_name, transaction_type, shares, price, "
            "transaction_date, filing_date) VALUES ($1, 'Seed', 'P', 5, 1.00, '2025-01-02', '2025-01-03') RETURNING id",
            cid)
        await conn.execute(
            "INSERT INTO surveillance_flags (transaction_id, company_id, event_date) VALUES ($1, $2, '2025-01-02')",
            dup_txn, cid)
    finally:
        await conn.close()

    applied = await migrate(url)
    assert applied == ["001_contradiction_pair_unique", "002_insider_txn_unique"]
    assert await migrate(url) == []  # idempotent

    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT COUNT(*) FROM contradictions") == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM insider_transactions") == 2
        seed = await conn.fetchrow(
            "SELECT transaction_type, transaction_code FROM insider_transactions WHERE id = $1", seeded_txn)
        assert tuple(seed) == ("buy", "P")  # hand-seeded raw code normalized
        assert await conn.fetchval("SELECT COUNT(*) FROM surveillance_flags") == 0  # cascaded with the duplicate
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO contradictions (claim_a_id, claim_b_id, company_id, similarity_score, nli_contradiction_score) "
                "VALUES ($1, $2, $3, 0.8, 0.9)", b, a, cid)
        col = await conn.fetchval(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'insider_transactions' AND column_name = 'shares'")
        assert col == "numeric"
    finally:
        await conn.close()

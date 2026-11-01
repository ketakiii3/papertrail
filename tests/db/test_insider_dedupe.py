"""F2: Form 4 rows are keyed by (accession_number, line_no); re-ingesting the
same filing stores nothing new and publishes nothing new."""

from datetime import date
from pathlib import Path

import asyncpg
import pytest

import edgar_ingester.form4_parser as form4_parser
from edgar_ingester.form4_parser import Form4Ingester, store_transactions
from shared.db import get_pool

pytestmark = pytest.mark.db

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "form4_sample.xml"
ACCESSION = "0001214156-25-000042"


@pytest.fixture
def published(monkeypatch):
    sent: list[tuple[str, dict]] = []

    async def fake_publish(topic, payload):
        sent.append((topic, payload))

    monkeypatch.setattr(form4_parser, "publish", fake_publish)
    return sent


@pytest.fixture
def transactions():
    return Form4Ingester.__new__(Form4Ingester).parse_form4_xml(FIXTURE.read_text())


async def _count(db_url, sql="SELECT COUNT(*) FROM insider_transactions"):
    conn = await asyncpg.connect(db_url)
    try:
        return await conn.fetchval(sql)
    finally:
        await conn.close()


async def test_ingesting_twice_stores_and_publishes_once(seeded, db_url, published, transactions):
    pool = await get_pool()
    filed = date(2025, 4, 7)

    first = await store_transactions(pool, seeded["company_id"], ACCESSION, filed, transactions)
    second = await store_transactions(pool, seeded["company_id"], ACCESSION, filed, transactions)

    assert first == 3
    assert second == 0
    assert await _count(db_url) == 3
    assert len(published) == 3
    assert [p["transaction_type"] for _, p in published] == ["sell", "other", "other"]
    # Fractional shares are stored, not truncated
    assert await _count(db_url, "SELECT shares FROM insider_transactions WHERE line_no = 0") == pytest.approx(4000.5)


async def test_pre_migration_row_is_adopted_not_duplicated(seeded, db_url, published, transactions):
    """A row stored before migration 002 (no accession, typed by A/D) gets the
    key and corrected type instead of a second copy."""
    conn = await asyncpg.connect(db_url)
    try:
        legacy_id = await conn.fetchval(
            """INSERT INTO insider_transactions
               (company_id, insider_name, insider_title, transaction_type, shares, price,
                total_value, transaction_date, filing_date)
               VALUES ($1, 'Doe Jane', 'Chief Executive Officer', 'sell', 10000, 210.00,
                       2100000, '2025-04-01', '2025-04-07') RETURNING id""",
            seeded["company_id"],
        )
    finally:
        await conn.close()

    pool = await get_pool()
    stored = await store_transactions(pool, seeded["company_id"], ACCESSION, date(2025, 4, 7), transactions)

    assert stored == 2  # the S and M rows; the F row was adopted
    assert await _count(db_url) == 3
    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow("SELECT * FROM insider_transactions WHERE id = $1", legacy_id)
    finally:
        await conn.close()
    assert (row["accession_number"], row["line_no"]) == (ACCESSION, 1)
    assert (row["transaction_type"], row["transaction_code"]) == ("other", "F")
    assert legacy_id not in [p["transaction_id"] for _, p in published]

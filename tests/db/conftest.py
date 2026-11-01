"""Fixtures for tests that need a real Postgres with pgvector.

Set TEST_DATABASE_URL to a server you can create databases on, e.g.

    docker run -d --rm --name pt-test-pg -p 55432:5432 \\
        -e POSTGRES_USER=papertrail -e POSTGRES_PASSWORD=papertrail pgvector/pgvector:pg16
    TEST_DATABASE_URL=postgresql://papertrail:papertrail@localhost:55432/postgres pytest -m db

Each test gets a freshly created database (`<name>_<pid>`), so the server's own
databases are never touched. Without TEST_DATABASE_URL, db tests are skipped.
"""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

import shared.db

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.getenv("TEST_DATABASE_URL")


def _with_db(url: str, dbname: str) -> str:
    return urlunparse(urlparse(url)._replace(path="/" + dbname))


async def _fresh_db(dbname: str, schema_sql: str) -> str:
    admin = await asyncpg.connect(ADMIN_URL)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()
    url = _with_db(ADMIN_URL, dbname)
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(schema_sql)
    finally:
        await conn.close()
    return url


async def _drop_db(dbname: str) -> None:
    admin = await asyncpg.connect(ADMIN_URL)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    finally:
        await admin.close()


def pytest_collection_modifyitems(config, items):
    if ADMIN_URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
async def make_db():
    """Factory: make_db(schema_sql) -> url of a new database with that schema applied."""
    created: list[str] = []

    async def factory(schema_sql: str) -> str:
        dbname = f"papertrail_test_{os.getpid()}_{len(created)}"
        created.append(dbname)
        return await _fresh_db(dbname, schema_sql)

    yield factory
    for dbname in created:
        await _drop_db(dbname)


@pytest.fixture
async def db_url(make_db, monkeypatch):
    """A database with the current infra/init.sql, wired into shared.db's pool."""
    url = await make_db((ROOT / "infra" / "init.sql").read_text())
    monkeypatch.setattr(shared.db.settings, "DATABASE_URL", url)
    await shared.db.close_pool()
    yield url
    await shared.db.close_pool()


@pytest.fixture
async def seeded(db_url):
    """One company, one filing, three claims. Returns their ids."""
    conn = await asyncpg.connect(db_url)
    try:
        company_id = await conn.fetchval(
            "INSERT INTO companies (ticker, name, cik) VALUES ('EXMP', 'Example Corp', '0000000001') RETURNING id"
        )
        filing_id = await conn.fetchval(
            """INSERT INTO filings (company_id, accession_number, form_type, filed_at, url)
               VALUES ($1, '0000000001-25-000001', '10-K', now(), 'https://example.test') RETURNING id""",
            company_id,
        )
        claim_ids = [
            await conn.fetchval(
                "INSERT INTO claims (filing_id, company_id, claim_text) VALUES ($1, $2, $3) RETURNING id",
                filing_id, company_id, text,
            )
            for text in ("claim one", "claim two", "claim three")
        ]
    finally:
        await conn.close()
    return {"company_id": company_id, "filing_id": filing_id, "claim_ids": claim_ids}

import asyncpg
from shared.config import settings


_pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_company_by_ticker(ticker: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM companies WHERE ticker = $1", ticker.upper())
    return dict(row) if row else None


async def get_company_by_id(company_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM companies WHERE id = $1", company_id)
    return dict(row) if row else None


async def insert_company(ticker: str, name: str, cik: str, sector: str = None, industry: str = None) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO companies (ticker, name, cik, sector, industry)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (ticker) DO UPDATE SET name = $2, sector = $4, industry = $5
           RETURNING id""",
        ticker.upper(), name, cik, sector, industry
    )
    return row["id"]


async def insert_filing(company_id: int, accession_number: str, form_type: str,
                        filed_at, url: str, period_of_report=None, raw_text=None) -> int | None:
    pool = await get_pool()
    try:
        row = await pool.fetchrow(
            """INSERT INTO filings (company_id, accession_number, form_type, filed_at, period_of_report, url, raw_text)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (accession_number) DO NOTHING
               RETURNING id""",
            company_id, accession_number, form_type, filed_at, period_of_report, url, raw_text
        )
        return row["id"] if row else None
    except Exception:
        return None


async def get_filing(filing_id: int) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM filings WHERE id = $1", filing_id)
    return dict(row) if row else None


async def mark_filing_processed(filing_id: int):
    pool = await get_pool()
    await pool.execute("UPDATE filings SET processed = true WHERE id = $1", filing_id)


async def insert_claims_batch(claims: list[dict]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO claims (filing_id, company_id, speaker, claim_text, claim_type,
                                   topic, sentiment, confidence, entities, temporal_ref,
                                   source_section, embedding, claim_date)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13)""",
            [(c["filing_id"], c["company_id"], c.get("speaker"), c["claim_text"],
              c.get("claim_type"), c.get("topic"), c.get("sentiment"), c.get("confidence"),
              c.get("entities", "{}"), c.get("temporal_ref"), c.get("source_section"),
              c.get("embedding"), c.get("claim_date")) for c in claims]
        )


async def get_similar_claims(embedding_str: str, company_id: int, exclude_filing_id: int,
                              limit: int = 20, threshold: float = 0.5):
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT id, filing_id, claim_text, claim_type, topic, sentiment, claim_date,
                  1 - (embedding <=> $1::vector) AS similarity
           FROM claims
           WHERE company_id = $2 AND filing_id != $3
             AND embedding IS NOT NULL
             AND 1 - (embedding <=> $1::vector) > $4
           ORDER BY embedding <=> $1::vector
           LIMIT $5""",
        embedding_str, company_id, exclude_filing_id, threshold, limit
    )
    return [dict(r) for r in rows]


async def get_insider_transactions_between(
    company_id: int, start_date, end_date
) -> list[dict]:
    """Form 4 insider rows with transaction_date in [start_date, end_date] (inclusive)."""
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT id, insider_name, insider_title, transaction_type, shares, price,
                  total_value, transaction_date, filing_date
           FROM insider_transactions
           WHERE company_id = $1
             AND transaction_date >= $2
             AND transaction_date <= $3
           ORDER BY transaction_date DESC""",
        company_id,
        start_date,
        end_date,
    )
    return [dict(r) for r in rows]


async def insert_contradiction(claim_a_id: int, claim_b_id: int, company_id: int,
                                similarity_score: float, nli_score: float,
                                severity: str, time_gap_days: int = None,
                                explanation: str = None,
                                agent_reasoning: str = None) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO contradictions (claim_a_id, claim_b_id, company_id,
                                       similarity_score, nli_contradiction_score,
                                       severity, time_gap_days, explanation,
                                       agent_reasoning)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           RETURNING id""",
        claim_a_id, claim_b_id, company_id, similarity_score, nli_score,
        severity, time_gap_days, explanation, agent_reasoning
    )
    return row["id"]

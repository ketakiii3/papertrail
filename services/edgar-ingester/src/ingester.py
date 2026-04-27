"""Main ingestion loop for SEC EDGAR filings."""

import asyncio
import logging
from datetime import datetime, date

from shared.db import get_pool, insert_company, insert_filing
from shared.kafka_client import publish
from .edgar_client import EdgarClient
from .sp500 import get_sp500_companies

logger = logging.getLogger(__name__)

FORM_TYPES = ["10-K", "10-Q", "8-K"]


async def seed_companies():
    """Seed the companies table with S&P 500 companies."""
    companies = get_sp500_companies()
    count = 0
    for c in companies:
        await insert_company(
            ticker=c["ticker"],
            name=c["name"],
            cik=c["cik"],
            sector=c.get("sector"),
            industry=c.get("industry"),
        )
        count += 1
    logger.info(f"Seeded {count} companies")
    return count


async def ingest_company(cik: str, company_id: int, client: EdgarClient):
    """Ingest recent filings for a single company."""
    filings = await client.get_company_filings(cik, form_types=FORM_TYPES, count=20)
    new_count = 0

    for f in filings:
        filed_at = datetime.strptime(f["filed_at"], "%Y-%m-%d").date() if isinstance(f["filed_at"], str) else f["filed_at"]
        period = None
        if f.get("period_of_report"):
            try:
                period = datetime.strptime(f["period_of_report"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Download filing text
        raw_text = await client.download_filing_text(f["url"])
        if not raw_text or len(raw_text) < 100:
            logger.warning(f"Skipping filing {f['accession_number']} - too short or empty")
            continue

        filing_id = await insert_filing(
            company_id=company_id,
            accession_number=f["accession_number"],
            form_type=f["form_type"],
            filed_at=filed_at,
            url=f["url"],
            period_of_report=period,
            raw_text=raw_text,
        )

        if filing_id:
            new_count += 1
            # Publish event for claim extraction
            await publish("filing.new", {
                "filing_id": filing_id,
                "company_id": company_id,
                "form_type": f["form_type"],
                "accession_number": f["accession_number"],
            })
            logger.info(f"Ingested filing {f['accession_number']} ({f['form_type']})")

    return new_count


async def run_ingestion():
    """Main ingestion loop - processes all S&P 500 companies."""
    logger.info("Starting EDGAR ingestion...")

    # Seed companies first
    await seed_companies()

    client = EdgarClient()
    pool = await get_pool()

    try:
        # Get all companies from DB
        rows = await pool.fetch("SELECT id, cik, ticker FROM companies WHERE sp500 = true")
        total_new = 0

        for row in rows:
            try:
                new = await ingest_company(row["cik"], row["id"], client)
                total_new += new
                logger.info(f"Company {row['ticker']}: {new} new filings")
            except Exception as e:
                logger.error(f"Failed to ingest {row['ticker']}: {e}")
                continue

        logger.info(f"Ingestion complete. {total_new} new filings total.")
    finally:
        await client.close()


async def run_continuous(interval_seconds: int = 3600):
    """Run ingestion continuously with a sleep interval."""
    while True:
        try:
            await run_ingestion()
        except Exception as e:
            logger.error(f"Ingestion cycle failed: {e}")
        logger.info(f"Sleeping {interval_seconds}s until next ingestion cycle...")
        await asyncio.sleep(interval_seconds)

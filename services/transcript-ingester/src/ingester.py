"""Earnings call transcript ingester.

Sources:
- SEC EDGAR exhibit filings (EX-99.1 often contains press releases / transcripts)
- Can be extended to support Seeking Alpha RSS or other sources.
"""

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from shared.config import settings
from shared.db import get_pool, insert_filing, get_company_by_ticker
from shared.redis_client import publish_event

logger = logging.getLogger(__name__)

EDGAR_BASE = "https://data.sec.gov"


class TranscriptIngester:
    def __init__(self):
        self._headers = {
            "User-Agent": settings.EDGAR_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = httpx.AsyncClient(headers=self._headers, timeout=30.0, follow_redirects=True)

    async def close(self):
        await self._client.aclose()

    async def fetch_8k_exhibits(self, cik: str, company_id: int, limit: int = 10):
        """Fetch 8-K filings and check for exhibit 99.1 (press releases / earnings)."""
        cik_padded = cik.lstrip("0").zfill(10)
        url = f"{EDGAR_BASE}/submissions/CIK{cik_padded}.json"

        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch submissions for CIK {cik}: {e}")
            return 0

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        count = 0
        for i in range(min(len(forms), limit)):
            if forms[i] != "8-K":
                continue

            accession = accessions[i]
            accession_no_dash = accession.replace("-", "")

            # Check the filing index for EX-99.1
            index_url = f"{EDGAR_BASE}/Archives/edgar/data/{cik_padded}/{accession_no_dash}/"
            try:
                idx_response = await self._client.get(index_url)
                await asyncio.sleep(0.1)  # Rate limit

                if idx_response.status_code != 200:
                    continue

                # Look for exhibit 99.1 in the filing
                soup = BeautifulSoup(idx_response.text, "lxml")
                exhibit_link = None
                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    text = a.get_text().lower()
                    if "ex-99" in href.lower() or "ex99" in href.lower() or "exhibit 99" in text:
                        exhibit_link = href if href.startswith("http") else f"{EDGAR_BASE}{href}"
                        break

                if not exhibit_link:
                    continue

                # Download exhibit text
                ex_response = await self._client.get(exhibit_link)
                await asyncio.sleep(0.1)

                if ex_response.status_code != 200:
                    continue

                raw_text = self._clean_html(ex_response.text)
                if len(raw_text) < 200:
                    continue

                # Check if it looks like an earnings release/transcript
                if not self._is_earnings_content(raw_text):
                    continue

                filed_at = datetime.strptime(dates[i], "%Y-%m-%d").date()
                filing_id = await insert_filing(
                    company_id=company_id,
                    accession_number=f"{accession}-EX99",
                    form_type="EX-99.1",
                    filed_at=filed_at,
                    url=exhibit_link,
                    raw_text=raw_text,
                )

                if filing_id:
                    await publish_event("filing.new", {
                        "filing_id": filing_id,
                        "company_id": company_id,
                        "form_type": "EX-99.1",
                        "is_transcript": True,
                    })
                    count += 1
                    logger.info(f"Ingested exhibit 99.1 from 8-K {accession}")

            except Exception as e:
                logger.error(f"Error processing 8-K {accession}: {e}")
                continue

        return count

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()[:500000]

    def _is_earnings_content(self, text: str) -> bool:
        """Heuristic check if text is earnings-related content."""
        lower = text.lower()
        keywords = ["earnings", "revenue", "quarter", "fiscal", "results",
                     "eps", "guidance", "outlook", "financial results"]
        matches = sum(1 for kw in keywords if kw in lower)
        return matches >= 3


async def run_transcript_ingestion():
    """Ingest transcripts for all tracked companies."""
    logger.info("Starting transcript ingestion...")
    pool = await get_pool()
    ingester = TranscriptIngester()

    try:
        companies = await pool.fetch("SELECT id, cik, ticker FROM companies WHERE sp500 = true")
        total = 0
        for c in companies:
            try:
                count = await ingester.fetch_8k_exhibits(c["cik"], c["id"])
                total += count
                if count:
                    logger.info(f"{c['ticker']}: {count} transcript exhibits ingested")
            except Exception as e:
                logger.error(f"Failed for {c['ticker']}: {e}")

        logger.info(f"Transcript ingestion complete: {total} new exhibits")
    finally:
        await ingester.close()

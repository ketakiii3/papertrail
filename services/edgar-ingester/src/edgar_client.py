"""SEC EDGAR API client with rate limiting."""

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from shared.config import settings

logger = logging.getLogger(__name__)

# SEC EDGAR rate limit: 10 requests per second
RATE_LIMIT = 10
BASE_URL = "https://data.sec.gov"
EFTS_URL = "https://efts.sec.gov/LATEST"


class EdgarClient:
    def __init__(self):
        self._semaphore = asyncio.Semaphore(RATE_LIMIT)
        self._headers = {
            "User-Agent": settings.EDGAR_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = httpx.AsyncClient(
            headers=self._headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        await self._client.aclose()

    async def _get(self, url: str) -> httpx.Response:
        async with self._semaphore:
            response = await self._client.get(url)
            response.raise_for_status()
            await asyncio.sleep(0.1)  # Respect rate limit
            return response

    async def get_company_filings(self, cik: str, form_types: list[str] = None,
                                   count: int = 40) -> list[dict]:
        """Fetch recent filings for a company from EDGAR."""
        cik_padded = cik.lstrip("0").zfill(10)
        url = f"{BASE_URL}/submissions/CIK{cik_padded}.json"

        try:
            response = await self._get(url)
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch filings for CIK {cik}: {e}")
            return []

        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        filings = []
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        report_dates = recent.get("reportDate", [])

        for i in range(min(len(forms), count)):
            form = forms[i]
            if form_types and form not in form_types:
                continue

            accession = accessions[i]
            accession_no_dash = accession.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            doc_url = f"{BASE_URL}/Archives/edgar/data/{cik_padded}/{accession_no_dash}/{primary_doc}"

            filing = {
                "accession_number": accession,
                "form_type": form,
                "filed_at": dates[i],
                "period_of_report": report_dates[i] if i < len(report_dates) and report_dates[i] else None,
                "url": doc_url,
                "cik": cik,
            }
            filings.append(filing)

        return filings

    async def download_filing_text(self, url: str) -> str:
        """Download and extract clean text from a filing."""
        try:
            response = await self._get(url)
            content_type = response.headers.get("content-type", "")

            if "html" in content_type or url.endswith(".htm") or url.endswith(".html"):
                return self._parse_html(response.text)
            else:
                return response.text[:500000]  # Cap at 500KB for safety
        except Exception as e:
            logger.error(f"Failed to download filing from {url}: {e}")
            return ""

    def _parse_html(self, html: str) -> str:
        """Extract clean text from HTML filing."""
        soup = BeautifulSoup(html, "lxml")

        # Remove script and style elements
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line and len(line) > 3:  # Skip very short lines
                lines.append(line)

        text = "\n".join(lines)

        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text[:500000]  # Cap at 500KB

    async def search_filings(self, query: str, date_from: str = None,
                              forms: list[str] = None) -> list[dict]:
        """Search EDGAR full-text search API."""
        params = {"q": query, "dateRange": "custom"}
        if date_from:
            params["startdt"] = date_from
        if forms:
            params["forms"] = ",".join(forms)

        url = f"{EFTS_URL}/search-index"
        try:
            response = await self._get(f"{EFTS_URL}/search-index?q={query}")
            data = response.json()
            return data.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.error(f"EDGAR search failed: {e}")
            return []

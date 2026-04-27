"""SEC Form 4 (insider transaction) XML parser and ingester."""

import asyncio
import logging
import re
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx

from shared.config import settings
from shared.db import get_pool
from shared.kafka_client import publish

logger = logging.getLogger(__name__)

BASE_URL = "https://data.sec.gov"


class Form4Ingester:
    def __init__(self):
        self._headers = {
            "User-Agent": settings.EDGAR_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
        self._semaphore = asyncio.Semaphore(10)
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
            await asyncio.sleep(0.1)
            return response

    async def fetch_form4_filings(self, cik: str, count: int = 40) -> list[dict]:
        """Fetch recent Form 4 filing index entries for a company."""
        cik_padded = cik.lstrip("0").zfill(10)
        url = f"{BASE_URL}/submissions/CIK{cik_padded}.json"

        try:
            response = await self._get(url)
            data = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch submissions for CIK {cik}: {e}")
            return []

        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        filings = []
        for i in range(min(len(forms), count)):
            if forms[i] not in ("4", "4/A"):
                continue

            accession = accessions[i]
            accession_no_dash = accession.replace("-", "")
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            doc_url = f"{BASE_URL}/Archives/edgar/data/{cik_padded}/{accession_no_dash}/{primary_doc}"

            filings.append({
                "accession_number": accession,
                "filed_at": dates[i],
                "url": doc_url,
                "cik": cik,
            })

        return filings

    def parse_form4_xml(self, xml_text: str) -> list[dict]:
        """Parse Form 4 XML into structured insider transaction records."""
        transactions = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            # Try extracting XML from HTML wrapper
            match = re.search(r"<ownershipDocument>.*?</ownershipDocument>", xml_text, re.DOTALL)
            if not match:
                return []
            try:
                root = ET.fromstring(match.group(0))
            except ET.ParseError:
                logger.warning("Failed to parse Form 4 XML")
                return []

        # Extract reporting owner info
        owner_el = root.find(".//reportingOwner")
        if owner_el is None:
            return []

        owner_id = owner_el.find("reportingOwnerId")
        owner_name = ""
        if owner_id is not None:
            name_el = owner_id.find("rptOwnerName")
            if name_el is not None and name_el.text:
                owner_name = name_el.text.strip()

        owner_rel = owner_el.find("reportingOwnerRelationship")
        owner_title = ""
        if owner_rel is not None:
            title_el = owner_rel.find("officerTitle")
            if title_el is not None and title_el.text:
                owner_title = title_el.text.strip()
            elif owner_rel.find("isDirector") is not None:
                is_dir = owner_rel.find("isDirector")
                if is_dir is not None and is_dir.text and is_dir.text.strip() == "1":
                    owner_title = "Director"

        # Parse non-derivative transactions
        for txn in root.findall(".//nonDerivativeTransaction"):
            record = self._parse_transaction(txn, owner_name, owner_title)
            if record:
                transactions.append(record)

        # Parse derivative transactions
        for txn in root.findall(".//derivativeTransaction"):
            record = self._parse_transaction(txn, owner_name, owner_title)
            if record:
                transactions.append(record)

        return transactions

    def _parse_transaction(self, txn_el, owner_name: str, owner_title: str) -> dict | None:
        """Parse a single transaction element."""
        # Transaction date
        date_el = txn_el.find(".//transactionDate/value")
        if date_el is None or not date_el.text:
            return None
        try:
            txn_date = datetime.strptime(date_el.text.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

        # Transaction type (acquisition/disposition)
        code_el = txn_el.find(".//transactionCoding/transactionCode")
        acq_disp_el = txn_el.find(".//transactionAmounts/transactionAcquiredDisposedCode/value")

        txn_code = code_el.text.strip() if code_el is not None and code_el.text else ""
        acq_disp = acq_disp_el.text.strip() if acq_disp_el is not None and acq_disp_el.text else ""

        # Map to buy/sell
        if acq_disp == "D":
            txn_type = "sell"
        elif acq_disp == "A":
            txn_type = "buy"
        else:
            txn_type = txn_code  # fallback

        # Shares
        shares_el = txn_el.find(".//transactionAmounts/transactionShares/value")
        shares = 0
        if shares_el is not None and shares_el.text:
            try:
                shares = float(shares_el.text.strip())
            except ValueError:
                pass

        # Price per share
        price_el = txn_el.find(".//transactionAmounts/transactionPricePerShare/value")
        price = 0.0
        if price_el is not None and price_el.text:
            try:
                price = float(price_el.text.strip())
            except ValueError:
                pass

        total_value = shares * price

        return {
            "insider_name": owner_name,
            "insider_title": owner_title,
            "transaction_type": txn_type,
            "shares": shares,
            "price": price,
            "total_value": total_value,
            "transaction_date": txn_date,
        }

    async def ingest_company_form4(self, cik: str, company_id: int) -> int:
        """Ingest Form 4 filings for a single company."""
        filings = await self.fetch_form4_filings(cik, count=40)
        new_count = 0
        pool = await get_pool()

        for f in filings:
            try:
                response = await self._get(f["url"])
                xml_text = response.text
            except Exception as e:
                logger.warning(f"Failed to download Form 4 {f['accession_number']}: {e}")
                continue

            transactions = self.parse_form4_xml(xml_text)
            if not transactions:
                continue

            filed_at = datetime.strptime(f["filed_at"], "%Y-%m-%d").date()

            for txn in transactions:
                try:
                    txn_id = await pool.fetchval(
                        """INSERT INTO insider_transactions
                           (company_id, insider_name, insider_title, transaction_type,
                            shares, price, total_value, transaction_date, filing_date)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                           ON CONFLICT DO NOTHING
                           RETURNING id""",
                        company_id,
                        txn["insider_name"],
                        txn["insider_title"],
                        txn["transaction_type"],
                        txn["shares"],
                        txn["price"],
                        txn["total_value"],
                        txn["transaction_date"],
                        filed_at,
                    )
                    if txn_id is None:
                        continue  # ON CONFLICT swallowed it; nothing new to publish
                    new_count += 1
                    await publish("insider.new", {
                        "transaction_id": txn_id,
                        "company_id": company_id,
                        "insider_name": txn["insider_name"],
                        "transaction_type": txn["transaction_type"],
                        "transaction_date": txn["transaction_date"].isoformat()
                            if hasattr(txn["transaction_date"], "isoformat")
                            else txn["transaction_date"],
                    })
                except Exception as e:
                    logger.warning(f"Failed to insert transaction: {e}")

        logger.info(f"Ingested {new_count} insider transactions for company {company_id}")
        return new_count


async def run_form4_ingestion():
    """Run Form 4 ingestion for all S&P 500 companies."""
    pool = await get_pool()
    ingester = Form4Ingester()

    try:
        rows = await pool.fetch("SELECT id, cik, ticker FROM companies WHERE sp500 = true")
        total = 0

        for row in rows:
            try:
                count = await ingester.ingest_company_form4(row["cik"], row["id"])
                total += count
                if count > 0:
                    logger.info(f"  {row['ticker']}: {count} insider transactions")
            except Exception as e:
                logger.error(f"Failed Form 4 ingestion for {row['ticker']}: {e}")

        logger.info(f"Form 4 ingestion complete. {total} total transactions.")
    finally:
        await ingester.close()

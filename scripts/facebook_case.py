"""Run the checker agent on the Facebook 2018 "materialized risk" case.

The SEC fined Facebook $100M (press release 2019-140) because its risk factors
kept saying users' data "may be improperly accessed" after it knew a developer
had misused data. The NLI filter scores this pair neutral (1.00), so the rules
never flag it; this checks whether the agent labels it `materialized_risk`.

Downloads the 10-K (2018-02-01) and 10-Q (2018-04-26) from EDGAR, then runs the
agent with tools that read those filings. Needs a tool-capable Ollama model:

    .venv/bin/python scripts/facebook_case.py llama3.2 qwen3:4b
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "contradiction-detector"))

from langchain_ollama import ChatOllama  # noqa: E402

from shared.config import settings  # noqa: E402
from src.checker import run_checker, surrounding_text  # noqa: E402

FILINGS = {
    "10-K": "https://www.sec.gov/Archives/edgar/data/1326801/000132680118000009/fb-12312017x10k.htm",
    "10-Q": "https://www.sec.gov/Archives/edgar/data/1326801/000132680118000032/fb-03312018x10q.htm",
}
A = ("However, if these third parties or developers fail to adopt or adhere to adequate data security practices, "
     "or in the event of a breach of their networks, our data or our users' data may be improperly accessed, "
     "used, or disclosed.")
B = ("In addition, in March 2018, we announced developments regarding the misuse of certain data by a developer "
     "that shared such data with third parties in violation of our terms and policies.")
CLAIMS = {1001: ("10-K", "2018-02-01", A), 1002: ("10-Q", "2018-04-26", B)}
PAIR = {
    "contradiction_id": 0, "company_id": 0, "ticker": "FB", "company_name": "Facebook, Inc.",
    "a": {"id": 1001, "text": A, "date": date(2018, 2, 1), "section": "Item 1A", "form": "10-K"},
    "b": {"id": 1002, "text": B, "date": date(2018, 4, 26), "section": "Item 1A", "form": "10-Q"},
    "nli": 0.0, "similarity": 0.72, "gap": 84, "severity": "low",
}


def fetch_text(url: str) -> str:
    html = httpx.get(url, headers={"User-Agent": settings.EDGAR_USER_AGENT}, timeout=60, follow_redirects=True).text
    return re.sub(r"\s+", " ", BeautifulSoup(html, "lxml").get_text(" "))


class FilingData:
    """The agent's tools, backed by the two downloaded filings instead of Postgres."""

    def __init__(self, text: dict[str, str]):
        self.text = text

    async def claim_context(self, company_id, claim_id):
        if claim_id not in CLAIMS:
            return None
        form, filed, sentence = CLAIMS[claim_id]
        return {"claim_id": claim_id, "form": form, "filed": filed, "section": "Item 1A. Risk Factors",
                "context": surrounding_text(self.text[form], sentence)}

    async def related_claims(self, company_id, exclude_ids, topic, date_from, date_to, limit):
        sentences = re.split(r"(?<=[.])\s+(?=[A-Z])", self.text["10-Q"])
        hits = [s for s in sentences if "misuse" in s and len(s) < 400]
        return [{"id": 2000 + i, "claim_date": "2018-04-26", "text": s} for i, s in enumerate(hits[:limit])]

    async def insider_trades(self, company_id, date_from, date_to):
        return []  # Form 4s not loaded for this offline case


async def main(models: list[str]) -> None:
    data = FilingData({form: fetch_text(url) for form, url in FILINGS.items()})
    for name in models:
        model = ChatOllama(model=name, base_url=settings.CHECKER_OLLAMA_URL, temperature=0, num_ctx=8192)
        run = await run_checker(PAIR, data, model)
        v = run["verdict"] or {}
        print(f"{name}: verdict={v.get('verdict')} severity={v.get('severity')} confidence={v.get('confidence')} "
              f"stop={run['stop_reason']} tool_calls={run['tool_calls']} {run['latency_ms']} ms")
        print(f"  tools: {[t['tool'] for t in run['trace']]}")
        print(f"  rationale: {v.get('rationale') or run['error']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or [settings.CHECKER_MODEL]))

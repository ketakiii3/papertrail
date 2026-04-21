"""Local LLM client using Ollama for agent reasoning."""

import logging
import httpx
from shared.config import settings

logger = logging.getLogger(__name__)

REASONING_PROMPT = """You are a financial analyst AI reviewing SEC filing contradictions.

Given two claims from the same company's SEC filings that contradict each other, provide a concise analysis explaining:
1. Why this contradiction matters to investors
2. What the financial/legal implications could be
3. Whether this suggests a material change in the company's outlook

Keep your response to 2-3 sentences. Be specific and cite the key differences.

Company: {company_name} ({ticker})

ORIGINAL CLAIM (from {date_a}, {section_a}):
"{claim_a}"

CONTRADICTING CLAIM (from {date_b}, {section_b}):
"{claim_b}"

Contradiction severity: {severity}
NLI score: {nli_score:.0%}
Time gap: {time_gap} days

Tool trace (structured pipeline outputs):
{tool_digest}

Analysis:"""


async def generate_reasoning(
    company_name: str,
    ticker: str,
    claim_a: str,
    claim_b: str,
    date_a: str,
    date_b: str,
    section_a: str,
    section_b: str,
    severity: str,
    nli_score: float,
    time_gap: int | None,
    tool_digest: str | None = None,
) -> str | None:
    """Generate agent reasoning for a contradiction using Ollama."""
    digest = (tool_digest or "(no tool digest)").strip()
    prompt = REASONING_PROMPT.format(
        company_name=company_name,
        ticker=ticker,
        claim_a=claim_a,
        claim_b=claim_b,
        date_a=date_a or "unknown",
        date_b=date_b or "unknown",
        section_a=section_a or "unknown",
        section_b=section_b or "unknown",
        severity=severity,
        nli_score=nli_score,
        time_gap=time_gap or "unknown",
        tool_digest=digest,
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 256,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            reasoning = data.get("response", "").strip()
            if reasoning:
                logger.info(f"Generated reasoning ({len(reasoning)} chars)")
                return reasoning
            return None
    except httpx.ConnectError:
        logger.warning("Ollama not available — skipping agent reasoning")
        return None
    except Exception as e:
        logger.error(f"Failed to generate reasoning: {e}")
        return None


async def ensure_model_available() -> bool:
    """Pull the configured model if not already available."""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Check if model exists
            resp = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                model_name = settings.OLLAMA_MODEL
                if any(model_name in m for m in models):
                    logger.info(f"Model '{model_name}' already available")
                    return True

            # Pull model
            logger.info(f"Pulling model '{settings.OLLAMA_MODEL}'...")
            resp = await client.post(
                f"{settings.OLLAMA_URL}/api/pull",
                json={"name": settings.OLLAMA_MODEL, "stream": False},
                timeout=600.0,
            )
            resp.raise_for_status()
            logger.info(f"Model '{settings.OLLAMA_MODEL}' ready")
            return True
    except Exception as e:
        logger.warning(f"Could not ensure model availability: {e}")
        return False

"""Filing text chunking and section segmentation."""

import re
import logging

logger = logging.getLogger(__name__)

# SEC filing section patterns
SECTION_PATTERNS_10K = {
    "Item 1": r"(?i)item\s+1[\.\s]+business",
    "Item 1A": r"(?i)item\s+1a[\.\s]+risk\s+factors",
    "Item 2": r"(?i)item\s+2[\.\s]+properties",
    "Item 7": r"(?i)item\s+7[\.\s]+management.s\s+discussion",
    "Item 7A": r"(?i)item\s+7a[\.\s]+quantitative",
    "Item 8": r"(?i)item\s+8[\.\s]+financial\s+statements",
}

SECTION_PATTERNS_8K = {
    "Item 1.01": r"(?i)item\s+1\.01",
    "Item 2.01": r"(?i)item\s+2\.01",
    "Item 2.02": r"(?i)item\s+2\.02",  # Results of Operations
    "Item 2.05": r"(?i)item\s+2\.05",  # Restructuring
    "Item 2.06": r"(?i)item\s+2\.06",
    "Item 5.02": r"(?i)item\s+5\.02",  # Director/Officer changes
    "Item 7.01": r"(?i)item\s+7\.01",
    "Item 8.01": r"(?i)item\s+8\.01",  # Other Events
    "Item 9.01": r"(?i)item\s+9\.01",
}

# Boilerplate patterns to filter out
BOILERPLATE_PATTERNS = [
    r"(?i)^table\s+of\s+contents",
    r"(?i)^this\s+(annual|quarterly)\s+report",
    r"(?i)^pursuant\s+to\s+the\s+requirements",
    r"(?i)^signatures?\s*$",
    r"(?i)^exhibit\s+\d+",
    r"(?i)^page\s+\d+",
    r"^\d+$",
    r"(?i)^forward.looking\s+statements?\s+disclaimer",
]

# Forward-looking / claim indicator patterns
CLAIM_INDICATORS = [
    r"(?i)\b(expect|anticipate|believe|estimate|project|forecast|plan|intend)\b",
    r"(?i)\b(guidance|outlook|target|goal)\b",
    r"(?i)\b(no\s+plans?\s+to|do\s+not\s+expect|will\s+not)\b",
    r"(?i)\b(revenue|earnings|margin|growth|decline|increase|decrease)\b",
    r"(?i)\b(restructur|layoff|workforce\s+reduction|headcount)\b",
    r"(?i)\b(acqui|merger|divest|spin.off)\b",
    r"(?i)\b(risk|uncertain|material|significant)\b",
    r"(?i)\b(million|billion|percent|%)\b",
    r"(?i)\b(fiscal\s+year|quarter|fy\d{2,4}|q[1-4])\b",
]


def split_into_sections(text: str, form_type: str) -> list[dict]:
    """Split filing text into sections based on form type."""
    if form_type in ("10-K", "10-Q"):
        patterns = SECTION_PATTERNS_10K
    elif form_type == "8-K":
        patterns = SECTION_PATTERNS_8K
    else:
        return [{"section": "full", "text": text}]

    sections = []
    section_starts = []

    for section_name, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            section_starts.append((match.start(), section_name))

    if not section_starts:
        return [{"section": "full", "text": text}]

    section_starts.sort(key=lambda x: x[0])

    for i, (start, name) in enumerate(section_starts):
        end = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(text)
        section_text = text[start:end].strip()
        if len(section_text) > 50:
            sections.append({"section": name, "text": section_text})

    return sections if sections else [{"section": "full", "text": text}]


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitter - handles common abbreviations
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Split on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

    cleaned = []
    for s in sentences:
        s = s.strip()
        if len(s) > 30 and len(s) < 2000:  # Skip very short/long
            if not any(re.match(p, s) for p in BOILERPLATE_PATTERNS):
                cleaned.append(s)

    return cleaned


def is_claim_sentence(sentence: str) -> bool:
    """Check if a sentence contains a potential claim."""
    matches = sum(1 for p in CLAIM_INDICATORS if re.search(p, sentence))
    return matches >= 2  # Require at least 2 indicators


def classify_claim_type(sentence: str) -> str:
    """Classify the type of claim."""
    s_lower = sentence.lower()

    if any(w in s_lower for w in ["expect", "anticipate", "forecast", "guidance", "outlook", "project"]):
        return "guidance"
    if any(w in s_lower for w in ["risk", "uncertain", "could adversely", "material adverse"]):
        return "risk"
    if any(w in s_lower for w in ["strategy", "plan to", "intend to", "initiative", "no plans"]):
        return "strategy"
    if any(w in s_lower for w in ["increased", "decreased", "reported", "generated", "achieved"]):
        return "factual"

    return "opinion"


def classify_topic(sentence: str) -> str:
    """Classify the topic of a claim."""
    s_lower = sentence.lower()

    topic_keywords = {
        "revenue": ["revenue", "sales", "top line", "top-line"],
        "profitability": ["margin", "profit", "earnings", "ebitda", "operating income", "net income"],
        "workforce": ["employee", "headcount", "workforce", "layoff", "restructur", "hiring"],
        "growth": ["growth", "expand", "increase", "scale"],
        "m&a": ["acqui", "merger", "divest", "spin-off", "buyout"],
        "regulatory": ["regulat", "compliance", "legal", "litigation", "sec ", "ftc"],
        "product": ["product", "launch", "r&d", "research", "innovation", "patent"],
        "capital": ["dividend", "buyback", "repurchase", "capex", "capital expenditure", "debt"],
        "supply_chain": ["supply chain", "supplier", "logistics", "inventory"],
        "macro": ["inflation", "interest rate", "recession", "macroeconomic", "geopolitical"],
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in s_lower for kw in keywords):
            return topic

    return "general"

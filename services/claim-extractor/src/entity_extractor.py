"""Named Entity Recognition using SpaCy."""

import json
import logging
import re

import spacy

logger = logging.getLogger(__name__)

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("SpaCy model not found, downloading...")
            from spacy.cli import download
            download("en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_entities(text: str) -> dict:
    """Extract named entities from text using SpaCy + custom financial rules."""
    nlp = get_nlp()
    doc = nlp(text[:10000])  # Cap input size

    entities = {
        "persons": [],
        "organizations": [],
        "money": [],
        "dates": [],
        "percentages": [],
    }

    for ent in doc.ents:
        if ent.label_ == "PERSON" and ent.text not in entities["persons"]:
            entities["persons"].append(ent.text)
        elif ent.label_ == "ORG" and ent.text not in entities["organizations"]:
            entities["organizations"].append(ent.text)
        elif ent.label_ == "MONEY" and ent.text not in entities["money"]:
            entities["money"].append(ent.text)
        elif ent.label_ == "DATE" and ent.text not in entities["dates"]:
            entities["dates"].append(ent.text)
        elif ent.label_ == "PERCENT" and ent.text not in entities["percentages"]:
            entities["percentages"].append(ent.text)

    # Custom financial entity patterns
    # Extract fiscal year/quarter references
    fiscal_refs = re.findall(r"(?i)(?:fy|fiscal\s+year)\s*\'?\d{2,4}", text)
    quarter_refs = re.findall(r"(?i)q[1-4]\s*(?:fy)?\s*\'?\d{2,4}", text)
    entities["dates"].extend(fiscal_refs + quarter_refs)

    # Extract dollar amounts that SpaCy might miss
    dollar_matches = re.findall(r"\$[\d,]+(?:\.\d+)?\s*(?:million|billion|thousand)?", text, re.IGNORECASE)
    for m in dollar_matches:
        if m not in entities["money"]:
            entities["money"].append(m)

    # Deduplicate
    for key in entities:
        entities[key] = list(set(entities[key]))[:10]  # Cap at 10 per type

    return entities


def extract_temporal_ref(text: str) -> str | None:
    """Extract temporal references from claim text."""
    patterns = [
        r"(?i)((?:fiscal\s+year|fy)\s*\'?\d{2,4})",
        r"(?i)(q[1-4]\s*(?:fy)?\s*\'?\d{2,4})",
        r"(?i)((?:first|second|third|fourth)\s+quarter\s+(?:of\s+)?\d{4})",
        r"(?i)((?:next|coming|this)\s+(?:quarter|year|fiscal\s+year))",
        r"(?i)(by\s+(?:the\s+)?end\s+of\s+\d{4})",
        r"(?i)(in\s+\d{4})",
        r"(?i)((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None

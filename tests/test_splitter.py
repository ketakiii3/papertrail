"""Tests for claim extraction splitter module."""

import sys
sys.path.insert(0, "/Users/ketaki.dabade/papertrail")

from services.claim_extractor.src.splitter import (
    extract_sentences,
    is_claim_sentence,
    classify_claim_type,
    classify_topic,
    split_into_sections,
)


def test_extract_sentences():
    text = (
        "Revenue grew 15% year over year. The company expects continued growth. "
        "This is boilerplate. We anticipate strong demand in Q3 FY25."
    )
    sentences = extract_sentences(text)
    assert len(sentences) >= 2
    assert any("Revenue grew" in s for s in sentences)


def test_is_claim_sentence():
    # Forward guidance with numbers = claim
    assert is_claim_sentence("We expect revenue growth of 8-10% in FY27.")
    # Strategy negation = claim
    assert is_claim_sentence("We have no plans to enter the automotive market or reduce workforce.")
    # Boilerplate = not a claim
    assert not is_claim_sentence("This document contains forward-looking statements.")
    # Too generic
    assert not is_claim_sentence("The sky is blue today.")


def test_classify_claim_type():
    assert classify_claim_type("We expect revenue growth of 8-10% next quarter.") == "guidance"
    assert classify_claim_type("Supply chain disruptions could materially affect operations.") == "risk"
    assert classify_claim_type("We plan to expand into European markets.") == "strategy"
    assert classify_claim_type("Revenue increased 15% to $5.2 billion.") == "factual"


def test_classify_topic():
    assert classify_topic("Revenue grew 15% year over year.") == "revenue"
    assert classify_topic("The company announced layoffs affecting 2,100 employees.") == "workforce"
    assert classify_topic("We completed the acquisition of WidgetCo.") == "m&a"
    assert classify_topic("Operating margins expanded to 28%.") == "profitability"
    assert classify_topic("We increased our quarterly dividend by 10%.") == "capital"


def test_split_into_sections_10k():
    text = (
        "Item 1. Business\nApple designs and manufactures consumer electronics.\n"
        "Item 1A. Risk Factors\nSupply chain risks could impact operations.\n"
        "Item 7. Management's Discussion and Analysis\nRevenue grew 15%.\n"
    )
    sections = split_into_sections(text, "10-K")
    assert len(sections) >= 2
    section_names = [s["section"] for s in sections]
    assert "Item 1" in section_names or "Item 1A" in section_names


def test_split_into_sections_8k():
    text = (
        "Item 2.02 Results of Operations\nThe company reported Q3 results.\n"
        "Item 9.01 Financial Statements\nSee attached exhibits.\n"
    )
    sections = split_into_sections(text, "8-K")
    assert len(sections) >= 1

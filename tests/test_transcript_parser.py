"""Tests for transcript parser."""

import sys
sys.path.insert(0, "/Users/ketaki.dabade/papertrail")

from services.transcript_ingester.src.transcript_parser import (
    parse_transcript,
    extract_speaker_claims,
    detect_title,
)


SAMPLE_TRANSCRIPT = """
Apple Inc. Q2 FY26 Earnings Call

Prepared Remarks

Tim Cook -- Chief Executive Officer:
Good afternoon everyone. Thank you for joining us. We are pleased to report another strong quarter with revenue of $97.3 billion. We continue to see incredible demand for iPhone and services. We have no plans for any material restructuring in the coming quarters.

Luca Maestri -- Chief Financial Officer:
Revenue grew 8% year over year to $97.3 billion. We expect continued momentum in services, which grew 15% this quarter. Our gross margin expanded to 46.2%, reflecting strong pricing and mix.

Questions and Answers

Analyst -- Morgan Stanley:
Can you provide more color on the services growth trajectory?

Tim Cook -- Chief Executive Officer:
We believe services will continue to grow at double-digit rates. The installed base is at an all-time high.
"""


def test_parse_transcript_segments():
    segments = parse_transcript(SAMPLE_TRANSCRIPT)
    assert len(segments) >= 3

    # Check speaker attribution
    speakers = [s.speaker for s in segments]
    assert "Tim Cook" in speakers
    assert "Luca Maestri" in speakers

    # Check section detection
    sections = [s.section for s in segments]
    assert "prepared_remarks" in sections
    assert "qa" in sections


def test_detect_title():
    assert detect_title("Chief Executive Officer") == "CEO"
    assert detect_title("CFO") == "CFO"
    assert detect_title("Vice President of Engineering") == "VP"
    assert detect_title("Random Person") is None


def test_speaker_claims_extraction():
    segments = parse_transcript(SAMPLE_TRANSCRIPT)
    claims = extract_speaker_claims(segments)
    assert len(claims) > 0

    # Each claim should have speaker attribution
    for claim in claims:
        assert claim["speaker"]
        assert claim["text"]
        assert claim["section"] in ("prepared_remarks", "qa")

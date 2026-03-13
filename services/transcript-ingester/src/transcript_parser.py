"""Earnings call transcript parser with speaker diarization."""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    speaker: str
    title: str | None
    text: str
    section: str  # "prepared_remarks" or "qa"


# Common executive title patterns
TITLE_PATTERNS = {
    r"(?i)\bCEO\b|chief\s+executive": "CEO",
    r"(?i)\bCFO\b|chief\s+financial": "CFO",
    r"(?i)\bCOO\b|chief\s+operating": "COO",
    r"(?i)\bCTO\b|chief\s+technology": "CTO",
    r"(?i)\bpresident\b": "President",
    r"(?i)\bvice\s+president\b|\bVP\b": "VP",
    r"(?i)\bdirector\b": "Director",
    r"(?i)\banalyst\b": "Analyst",
}


def detect_title(name_line: str) -> str | None:
    """Detect executive title from speaker line."""
    for pattern, title in TITLE_PATTERNS.items():
        if re.search(pattern, name_line):
            return title
    return None


def parse_transcript(text: str) -> list[TranscriptSegment]:
    """Parse an earnings call transcript into speaker-attributed segments.

    Handles common transcript formats:
    - "Speaker Name -- Title" followed by remarks
    - "Speaker Name:" followed by remarks
    - Section headers like "Prepared Remarks" and "Q&A"
    """
    segments = []
    current_section = "prepared_remarks"

    # Detect Q&A section transition
    qa_patterns = [
        r"(?i)questions?\s+and\s+answers?",
        r"(?i)Q\s*&\s*A\s+session",
        r"(?i)operator.*questions",
    ]

    # Speaker line patterns
    speaker_pattern = re.compile(
        r"^([A-Z][a-zA-Z\s\.]+?)(?:\s*[-—–]\s*(.+?))?(?:\s*:|\s*$)",
        re.MULTILINE,
    )

    lines = text.split("\n")
    current_speaker = None
    current_title = None
    current_text_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for Q&A section transition
        for qa_pat in qa_patterns:
            if re.search(qa_pat, stripped):
                # Save previous segment
                if current_speaker and current_text_lines:
                    segments.append(TranscriptSegment(
                        speaker=current_speaker,
                        title=current_title,
                        text=" ".join(current_text_lines),
                        section=current_section,
                    ))
                    current_text_lines = []
                current_section = "qa"
                break

        # Check for new speaker
        match = speaker_pattern.match(stripped)
        if match and len(match.group(1).split()) <= 5:  # Names shouldn't be too long
            # Save previous segment
            if current_speaker and current_text_lines:
                segments.append(TranscriptSegment(
                    speaker=current_speaker,
                    title=current_title,
                    text=" ".join(current_text_lines),
                    section=current_section,
                ))
                current_text_lines = []

            current_speaker = match.group(1).strip()
            title_text = match.group(2) or ""
            current_title = detect_title(title_text) or detect_title(current_speaker)

            # Check if there's text on the same line after the speaker
            remainder = stripped[match.end():].strip()
            if remainder:
                current_text_lines.append(remainder)
        else:
            # Continue current speaker's text
            if current_speaker:
                current_text_lines.append(stripped)

    # Don't forget the last segment
    if current_speaker and current_text_lines:
        segments.append(TranscriptSegment(
            speaker=current_speaker,
            title=current_title,
            text=" ".join(current_text_lines),
            section=current_section,
        ))

    return segments


def extract_speaker_claims(segments: list[TranscriptSegment]) -> list[dict]:
    """Extract individual claims from transcript segments, preserving speaker attribution."""
    claims = []

    for segment in segments:
        # Split segment text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', segment.text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30 or len(sentence) > 2000:
                continue

            claims.append({
                "text": sentence,
                "speaker": segment.speaker,
                "speaker_title": segment.title,
                "section": segment.section,
            })

    return claims

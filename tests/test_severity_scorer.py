"""Tests for severity scoring model."""

import sys
sys.path.insert(0, "/Users/ketaki.dabade/papertrail")

from models.severity_scorer.scorer import score_severity, SeverityInput, compute_specificity


def test_high_severity_contradiction():
    result = score_severity(SeverityInput(
        nli_score=0.95,
        similarity=0.89,
        time_gap_days=30,
        claim_a_text='We have no plans for any material restructuring or workforce reduction.',
        claim_b_text='The Company announced a restructuring plan affecting 2,100 employees.',
        topic="workforce",
        insider_sells_between=3,
        insider_sell_value=2_500_000,
    ))
    assert result["severity"] in ("high", "critical")
    assert result["score"] > 0.6


def test_low_severity_boilerplate():
    result = score_severity(SeverityInput(
        nli_score=0.55,
        similarity=0.5,
        time_gap_days=365,
        claim_a_text="We may face macroeconomic headwinds.",
        claim_b_text="Economic conditions remain uncertain.",
        topic="macro",
    ))
    assert result["severity"] in ("low", "medium")
    assert result["score"] < 0.5


def test_specificity_scoring():
    # Specific claim with numbers
    score = compute_specificity("We expect revenue growth of 8-10% in FY27.")
    assert score > 0.3

    # Vague claim
    score = compute_specificity("The market may experience challenges.")
    assert score < 0.3

    # Strong negation
    score = compute_specificity("We have no plans to restructure.")
    assert score > 0.2


def test_insider_context_increases_severity():
    base = SeverityInput(
        nli_score=0.8,
        similarity=0.7,
        time_gap_days=60,
        claim_a_text="Operations remain strong.",
        claim_b_text="Significant operational challenges emerged.",
        topic="general",
    )

    without_insider = score_severity(base)

    with_insider = score_severity(SeverityInput(
        **{**base.__dict__, "insider_sells_between": 5, "insider_sell_value": 5_000_000}
    ))

    assert with_insider["score"] > without_insider["score"]

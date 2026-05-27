"""Tests for Sr Wall Street advisor."""

from unittest.mock import patch

import pytest

from ai.wall_street_advisor import (
    ResearchRating,
    generate_research_note,
    _derive_rating,
    _conviction_score,
)
from analysis.integrated_analysis import IntegratedAnalysis


def _sample_integrated(composite=72, tech=70, sent=68, label="BULLISH"):
    return IntegratedAnalysis(
        ticker="NVDA",
        price=900.0,
        technical_score=tech,
        sentiment_score=sent,
        news_score=65,
        composite_score=composite,
        signal="BUY_CANDIDATE",
        explanation="Strong uptrend with volume",
        sentiment_label=label,
        analyst_consensus="BUY",
        catalyst_notes="AI demand catalyst",
        sector="technology",
    )


def test_derive_rating_highly_attractive():
    assert _derive_rating(75, "BULLISH", 70) == ResearchRating.HIGHLY_ATTRACTIVE


def test_derive_rating_high_risk():
    assert _derive_rating(35, "BEARISH", 40) == ResearchRating.HIGH_RISK


def test_conviction_penalizes_divergence():
    aligned = _conviction_score(70, 68, 67)
    diverged = _conviction_score(70, 90, 40)
    assert aligned > diverged


@patch("ai.analyst.call_ai_stock", return_value=(None, "rule-based"))
def test_generate_research_note_structure(mock_ai):
    note = generate_research_note(_sample_integrated(), account_equity=50_000, daily_target_pct=3.0)
    assert note.ticker == "NVDA"
    assert note.is_actionable is False
    assert note.rating in ResearchRating
    assert note.executive_summary
    assert note.bull_case
    assert note.bear_case
    assert "NOT FINANCIAL ADVICE" in note.full_report
    assert note.ai_powered is False

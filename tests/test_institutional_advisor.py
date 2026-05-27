"""Tests for institutional AI advisor personas."""

from unittest.mock import patch

import pytest

from ai.institutional_advisor import (
    AdvisorPersona,
    DAILY_TARGET_PRESETS,
    explain_batch_summary,
    explain_integrated,
    get_persona_weights,
    scale_target_table,
)
from analysis.integrated_analysis import IntegratedAnalysis


def test_persona_weights_sum_reasonable():
    for persona in AdvisorPersona:
        tw, sw, nw = get_persona_weights(persona)
        assert tw + sw + nw == pytest.approx(1.0)


def test_daily_target_presets_include_user_ranges():
    assert DAILY_TARGET_PRESETS["Active 3%"] == 3.0
    assert DAILY_TARGET_PRESETS["Aggressive 5%"] == 5.0
    assert DAILY_TARGET_PRESETS["High 10%"] == 10.0
    assert DAILY_TARGET_PRESETS["Extreme 20%"] == 20.0


def test_scale_target_table_scales_with_equity():
    rows = scale_target_table(100_000, pcts=[3, 10])
    assert rows[0]["Daily $"] == "$3,000"
    assert rows[1]["Daily $"] == "$10,000"


def _sample_analysis(ticker="AAPL") -> IntegratedAnalysis:
    return IntegratedAnalysis(
        ticker=ticker,
        price=180.0,
        technical_score=78,
        sentiment_score=65,
        news_score=70,
        composite_score=72,
        signal="BUY_CANDIDATE",
        explanation="Strong trend",
        sentiment_label="BULLISH",
        analyst_consensus="BUY",
        catalyst_notes="Product launch",
    )


@patch("ai.analyst.call_ai_stock", return_value=(None, "rule-based"))
def test_explain_integrated_rule_based_fallback(mock_ai):
    advice = explain_integrated(
        _sample_analysis(),
        AdvisorPersona.BUFFETT,
        daily_target_pct=5.0,
        account_equity=50_000,
    )
    assert advice.is_actionable is False
    assert advice.ticker == "AAPL"
    assert "NOT FINANCIAL ADVICE" in advice.full_text
    assert advice.ai_powered is False
    mock_ai.assert_called_once()


@patch("ai.analyst.call_ai", return_value=("AI market summary.", "gemini"))
def test_explain_batch_summary_ai(mock_ai):
    analyses = [_sample_analysis("AAPL"), _sample_analysis("MSFT")]
    advice = explain_batch_summary(analyses, AdvisorPersona.VANGUARD, 3.0, 25_000)
    assert advice.ai_powered is True
    assert "AI market summary" in advice.narrative
    assert advice.is_actionable is False

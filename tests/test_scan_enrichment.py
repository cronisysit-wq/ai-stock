"""Tests for batch scan AI enrichment."""

from unittest.mock import patch

from analysis.strategy_sentiment_scanner import StrategySentimentRow, ACTION_STRONG_BUY, ACTION_INVEST
from ai.scan_enrichment import _parse_batch_response, enrich_scan_rows


def test_parse_batch_response():
    text = "NVDA|Strong momentum and bullish sentiment align with technical breakout.\nAAPL|Steady trend with neutral news."
    notes = _parse_batch_response(text)
    assert "NVDA" in notes
    assert "AAPL" in notes


@patch("ai.analyst.call_ai_scan", return_value=(
    "NVDA|Educational note about momentum.\nAAPL|Educational note about stability.",
    "gemini",
))
def test_enrich_scan_rows(mock_scan):
    rows = [
        StrategySentimentRow(ticker="NVDA", price=100, suggested_action=ACTION_STRONG_BUY, composite_score=75),
        StrategySentimentRow(ticker="AAPL", price=180, suggested_action=ACTION_INVEST, composite_score=68),
    ]
    n, prov = enrich_scan_rows(rows, top_n=5)
    assert n == 2
    assert prov == "gemini"
    assert rows[0].ai_note
    assert rows[0].ai_provider == "gemini"

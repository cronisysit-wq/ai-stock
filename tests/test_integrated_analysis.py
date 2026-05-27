"""Tests for integrated technical + sentiment analysis."""

from unittest.mock import MagicMock, patch

import pytest

from analysis.integrated_analysis import (
    IntegratedAnalysis,
    IntegratedAnalyzer,
    compute_composite_score,
)


def test_compute_composite_score_weighted_average():
    score = compute_composite_score(80, 60, 70, 0.5, 0.3, 0.2)
    assert score == pytest.approx(72.0)


def test_compute_composite_score_clamps():
    assert compute_composite_score(150, 150, 150) == 100.0
    assert compute_composite_score(-10, -10, -10) == 0.0


def test_integrated_analysis_top_headlines():
    item = MagicMock()
    item.title = "Earnings beat expectations"
    ia = IntegratedAnalysis(
        ticker="AAPL",
        price=180.0,
        technical_score=75,
        sentiment_score=65,
        news_score=70,
        composite_score=72,
        signal="BUY_CANDIDATE",
        news_headlines=[item],
    )
    assert ia.top_headlines == ["Earnings beat expectations"]


@patch("analysis.integrated_analysis.SentimentAnalyzer")
def test_analyze_ticker_uses_sentiment(mock_sent_cls):
    mock_sent = MagicMock()
    mock_sent.is_valid = True
    mock_sent.overall_sentiment_score = 80.0
    mock_sent.news_sentiment_score = 75.0
    mock_sent.overall_sentiment_label = "BULLISH"
    mock_sent.analyst_recommendation = "BUY"
    mock_sent.catalyst_notes = "Earnings next week"
    mock_sent.news_items = []
    mock_sent_cls.return_value.analyze.return_value = mock_sent

    analyzer = IntegratedAnalyzer(max_workers=1)
    result = analyzer.analyze_ticker("MSFT", 400.0, 85.0, signal="BUY_CANDIDATE")

    assert result.ticker == "MSFT"
    assert result.sentiment_label == "BULLISH"
    assert result.composite_score > 80


def test_enrich_batch_sorts_by_composite():
    analyzer = IntegratedAnalyzer(max_workers=1)

    def fake_analyze(ticker, **kwargs):
        scores = {"AAA": 90, "BBB": 70}
        tech = scores.get(ticker, 50)
        return IntegratedAnalysis(
            ticker=ticker,
            price=10.0,
            technical_score=tech,
            sentiment_score=50,
            news_score=50,
            composite_score=tech,
            signal="WATCH",
        )

    with patch.object(analyzer, "analyze_ticker", side_effect=fake_analyze):
        out = analyzer.enrich_batch([
            {"ticker": "BBB", "price": 10, "technical_score": 70},
            {"ticker": "AAA", "price": 10, "technical_score": 90},
        ])
    assert [r.ticker for r in out] == ["AAA", "BBB"]

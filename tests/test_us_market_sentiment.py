"""Tests for US market sentiment scanner."""

from unittest.mock import MagicMock, patch

import pytest

from analysis.us_market_sentiment import (
    USMarketSentimentScanner,
    USSentimentRow,
    USMarketSentimentSession,
)


def _mock_sentiment(ticker: str, score: float = 70.0, label: str = "BULLISH"):
    sent = MagicMock()
    sent.is_valid = True
    sent.sector = "technology"
    sent.industry = "Software"
    sent.overall_sentiment_score = score
    sent.news_sentiment_score = score - 5
    sent.analyst_score = score + 2
    sent.overall_sentiment_label = label
    sent.sentiment_momentum = 10.0
    sent.earnings_tone = "NEUTRAL"
    sent.social_buzz_score = 60.0
    sent.analyst_recommendation = "BUY"
    sent.price_vs_target_pct = 12.0
    sent.bullish_headlines = 3
    sent.bearish_headlines = 1
    sent.catalyst_notes = "Earnings next week"
    sent.market_trend = "BULLISH"
    sent.error = ""
    return sent


@patch("yfinance.Ticker")
@patch("analysis.us_market_sentiment.get_universe", return_value=["AAPL", "MSFT"])
def test_scan_ranks_by_sentiment(mock_universe, mock_yf):
    mock_yf.return_value.info = {"currentPrice": 100.0}
    scanner = USMarketSentimentScanner(max_workers=2, top_n=10)
    scores = {"AAPL": 75.0, "MSFT": 85.0}

    def analyze_side_effect(ticker, current_price=0):
        return _mock_sentiment(ticker, scores.get(ticker, 50))

    scanner.analyzer = MagicMock()
    scanner.analyzer.analyze.side_effect = analyze_side_effect

    session = scanner.scan(preset="sp500")

    assert session.scanned == 2
    assert session.results[0].ticker == "MSFT"
    assert session.results[0].rank == 1
    assert session.market_bullish_pct == 100.0


def test_sector_breadth_computation():
    rows = [
        USSentimentRow(ticker="A", sector="technology", overall_score=70, sentiment_label="BULLISH", price=1),
        USSentimentRow(ticker="B", sector="technology", overall_score=60, sentiment_label="NEUTRAL", price=1),
        USSentimentRow(ticker="C", sector="energy", overall_score=40, sentiment_label="BEARISH", price=1),
    ]
    scanner = USMarketSentimentScanner(max_workers=1, top_n=10)
    breadth = scanner._compute_sector_breadth(rows)
    tech = next(b for b in breadth if b.sector == "technology")
    assert tech.count == 2
    assert tech.avg_sentiment == 65.0
    assert tech.bullish_pct == 50.0

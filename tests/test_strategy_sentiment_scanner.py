"""Tests for unified strategy + sentiment scanner."""

from unittest.mock import MagicMock, patch

from analysis.strategy_sentiment_scanner import (
    StrategySentimentScanner,
    StrategySentimentRow,
    _suggested_action,
    _build_why,
    _sort_key,
    _rank_rows,
    ACTION_STRONG_BUY,
    ACTION_INVEST,
)
from analysis.stock_analyzer import SIGNAL_BUY_CANDIDATE


def test_suggested_action_strong_buy():
    assert _suggested_action(70, SIGNAL_BUY_CANDIDATE, "BULLISH", 60, "STRONG BUY") == ACTION_STRONG_BUY


def test_suggested_action_invest():
    assert _suggested_action(70, SIGNAL_BUY_CANDIDATE, "BULLISH", 60, "BUY") == ACTION_INVEST


def test_suggested_action_avoid():
    assert _suggested_action(35, "AVOID", "BEARISH", 30) == "AVOID"


def test_sort_key_strong_buy_first():
    strong = StrategySentimentRow(
        ticker="NVDA", price=100, suggested_action=ACTION_STRONG_BUY,
        composite_score=75, analyst="STRONG BUY", strategy_score=70, sentiment_score=65,
    )
    invest = StrategySentimentRow(
        ticker="AAPL", price=100, suggested_action=ACTION_INVEST,
        composite_score=90, analyst="BUY", strategy_score=85, sentiment_score=80,
    )
    assert _sort_key(strong) < _sort_key(invest)


def test_rank_rows_puts_strong_buy_on_top():
    rows = [
        StrategySentimentRow(ticker="A", price=1, suggested_action=ACTION_INVEST, composite_score=90, analyst="BUY"),
        StrategySentimentRow(ticker="B", price=1, suggested_action=ACTION_STRONG_BUY, composite_score=70, analyst="STRONG BUY"),
    ]
    ranked = _rank_rows(rows)
    assert ranked[0].ticker == "B"
    assert ranked[0].rank == 1


def test_avoid_with_strong_analyst_not_above_invest():
    """Analyst STRONG BUY must not outrank Action INVEST."""
    rows = [
        StrategySentimentRow(ticker="BAD", price=1, suggested_action="AVOID", composite_score=99, analyst="STRONG BUY"),
        StrategySentimentRow(ticker="GOOD", price=1, suggested_action=ACTION_INVEST, composite_score=50, analyst="BUY"),
        StrategySentimentRow(ticker="MID", price=1, suggested_action="WATCH", composite_score=60, analyst="HOLD"),
    ]
    ranked = _rank_rows(rows)
    assert [r.ticker for r in ranked] == ["GOOD", "MID", "BAD"]


def test_analyst_order_within_same_action():
    rows = [
        StrategySentimentRow(ticker="C", price=1, suggested_action=ACTION_INVEST, composite_score=80, analyst="HOLD"),
        StrategySentimentRow(ticker="A", price=1, suggested_action=ACTION_INVEST, composite_score=80, analyst="STRONG BUY"),
        StrategySentimentRow(ticker="B", price=1, suggested_action=ACTION_INVEST, composite_score=80, analyst="BUY"),
    ]
    ranked = _rank_rows(rows)
    assert [r.ticker for r in ranked] == ["A", "B", "C"]


def test_build_why_includes_both():
    row = StrategySentimentRow(
        ticker="AAPL",
        price=180,
        strategy_signal=SIGNAL_BUY_CANDIDATE,
        strategy_score=72,
        sentiment_score=65,
        sentiment_label="BULLISH",
        analyst="BUY",
        suggested_action=ACTION_STRONG_BUY,
    )
    why = _build_why(row)
    assert "Strategy" in why
    assert "Sentiment" in why


@patch("analysis.strategy_sentiment_scanner.get_universe", return_value=["AAPL", "MSFT"])
@patch("analysis.strategy_sentiment_scanner._resolve_price", side_effect=lambda t, f, i: (f, "live", ""))
def test_scan_ranks_strong_buy_first(mock_price, mock_uni):
    scanner = StrategySentimentScanner(max_workers=2)

    def fake_analyze(ticker, **kwargs):
        scores = {"AAPL": 80, "MSFT": 60}
        sig = SIGNAL_BUY_CANDIDATE if ticker == "AAPL" else "WATCH"
        return MagicMock(
            error=None,
            current_price=100.0,
            signal=sig,
            overall_score=scores[ticker],
            stop_loss_price=95.0,
            take_profit_price=110.0,
            indicators={"price_source": "live"},
        )

    def fake_sentiment(ticker, current_price=0):
        if ticker == "AAPL":
            return MagicMock(
                is_valid=True,
                overall_sentiment_score=70,
                news_sentiment_score=70,
                overall_sentiment_label="BULLISH",
                analyst_recommendation="STRONG BUY",
                sector="technology",
                sentiment_momentum=5.0,
                earnings_tone="NEUTRAL",
            )
        return MagicMock(
            is_valid=True,
            overall_sentiment_score=50,
            news_sentiment_score=50,
            overall_sentiment_label="NEUTRAL",
            analyst_recommendation="HOLD",
            sector="technology",
            sentiment_momentum=0.0,
            earnings_tone="NEUTRAL",
        )

    scanner.analyzer = MagicMock()
    scanner.analyzer.analyze.side_effect = fake_analyze
    scanner.analyzer.stop_loss_pct = 2.0
    scanner.analyzer.take_profit_pct = 5.0
    scanner.sentiment = MagicMock()
    scanner.sentiment.analyze.side_effect = fake_sentiment

    session = scanner.scan(preset="robinhood")
    assert session.scanned == 2
    assert session.results[0].ticker == "AAPL"
    assert session.results[0].suggested_action == ACTION_STRONG_BUY

"""
Tests for analysis/stock_analyzer.py

Tests:
  1. StockAnalysis dataclass fields are populated on success
  2. Error is set when ticker is invalid
  3. Overall score is in [0, 100]
  4. Signal is one of the valid values
  5. Stop loss is below current price
  6. Take profit is above current price
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _make_mock_df(n=100, price=150.0):
    """Build a mock OHLCV DataFrame for testing."""
    dates = pd.date_range(end=datetime.today(), periods=n, freq="1D")
    prices = [price + np.random.uniform(-5, 5) for _ in range(n)]
    df = pd.DataFrame({
        "Open":   [p * 0.998 for p in prices],
        "High":   [p * 1.01  for p in prices],
        "Low":    [p * 0.99  for p in prices],
        "Close":  prices,
        "Volume": [1_000_000 + np.random.randint(0, 500_000) for _ in range(n)],
    }, index=dates)
    return df


@pytest.fixture
def analyzer():
    from analysis.stock_analyzer import StockAnalyzer
    return StockAnalyzer(stop_loss_pct=2.0, take_profit_pct=5.0)


class TestStockAnalyzer:

    def test_successful_analysis_populates_fields(self, analyzer):
        """All core fields must be populated for a valid ticker."""
        mock_df = _make_mock_df()
        with patch("analysis.stock_analyzer.get_historical_data", return_value=mock_df):
            result = analyzer.analyze("AAPL")
        assert result.ticker == "AAPL"
        assert result.current_price > 0
        assert result.error is None or result.error == ""

    def test_invalid_ticker_sets_error(self, analyzer):
        """Empty DataFrame (bad ticker) must set the error field."""
        with patch("analysis.stock_analyzer.get_historical_data", return_value=pd.DataFrame()):
            result = analyzer.analyze("XXXINVALID999")
        assert result.error is not None and result.error != ""

    def test_overall_score_in_range(self, analyzer):
        """Overall score must be 0–100."""
        mock_df = _make_mock_df()
        with patch("analysis.stock_analyzer.get_historical_data", return_value=mock_df):
            result = analyzer.analyze("MSFT")
        if not result.error:
            assert 0 <= result.overall_score <= 100

    def test_signal_is_valid(self, analyzer):
        """Signal must be one of the four canonical values."""
        from analysis.stock_analyzer import (
            SIGNAL_BUY_CANDIDATE, SIGNAL_SELL_CANDIDATE,
            SIGNAL_WATCH, SIGNAL_AVOID,
        )
        valid_signals = {SIGNAL_BUY_CANDIDATE, SIGNAL_SELL_CANDIDATE, SIGNAL_WATCH, SIGNAL_AVOID}
        mock_df = _make_mock_df()
        with patch("analysis.stock_analyzer.get_historical_data", return_value=mock_df):
            result = analyzer.analyze("NVDA")
        if not result.error:
            assert result.signal in valid_signals

    def test_stop_loss_below_price(self, analyzer):
        """Stop loss price must be strictly below current price."""
        mock_df = _make_mock_df(price=200.0)
        with patch("analysis.stock_analyzer.get_historical_data", return_value=mock_df):
            result = analyzer.analyze("TSLA")
        if not result.error and result.current_price > 0:
            assert result.stop_loss_price < result.current_price

    def test_take_profit_above_price(self, analyzer):
        """Take profit price must be strictly above current price."""
        mock_df = _make_mock_df(price=200.0)
        with patch("analysis.stock_analyzer.get_historical_data", return_value=mock_df):
            result = analyzer.analyze("GOOGL")
        if not result.error and result.current_price > 0:
            assert result.take_profit_price > result.current_price

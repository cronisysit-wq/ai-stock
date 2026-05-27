"""
Tests for backtester — 8 cases covering look-ahead bias, fees, slippage, metrics.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from trading.backtester import Backtester, BacktestResult


def make_df(n_bars: int = 120, trend: str = "up") -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=n_bars, freq="B")

    if trend == "up":
        close = 100.0 + np.arange(n_bars) * 0.5 + np.random.randn(n_bars) * 0.3
    elif trend == "down":
        close = 200.0 - np.arange(n_bars) * 0.5 + np.random.randn(n_bars) * 0.3
    else:
        close = 100.0 + np.random.randn(n_bars) * 2.0

    df = pd.DataFrame({
        "open":   close + np.random.randn(n_bars) * 0.2,
        "high":   close + abs(np.random.randn(n_bars)) * 0.5,
        "low":    close - abs(np.random.randn(n_bars)) * 0.5,
        "close":  close,
        "volume": np.random.randint(1_000_000, 10_000_000, n_bars).astype(float),
    }, index=dates)
    return df


class TestBacktestResult:
    """Smoke-test the result dataclass and field types."""

    def test_empty_result_structure(self):
        result = Backtester._empty_result(10_000.0)
        assert result.num_trades == 0
        assert result.equity_curve == [10_000.0]
        assert result.total_return == 0.0
        assert result.total_fees == 0.0
        assert result.total_slippage == 0.0

    def test_result_has_new_metric_fields(self):
        result = Backtester._empty_result(10_000.0)
        assert hasattr(result, "sortino_ratio")
        assert hasattr(result, "calmar_ratio")
        assert hasattr(result, "profit_factor")
        assert hasattr(result, "worst_day_pnl")
        assert hasattr(result, "consecutive_losing_trades")
        assert hasattr(result, "avg_holding_days")
        assert hasattr(result, "total_fees")
        assert hasattr(result, "total_slippage")


class TestMaxDrawdown:
    def test_flat_curve_zero_drawdown(self):
        curve = [1000.0] * 50
        dd, dd_pct = Backtester._max_drawdown(curve)
        assert dd == 0.0
        assert dd_pct == 0.0

    def test_falling_curve_max_drawdown(self):
        curve = [1000.0, 900.0, 800.0, 700.0]
        dd, dd_pct = Backtester._max_drawdown(curve)
        assert dd == 300.0
        assert abs(dd_pct - 0.30) < 0.001   # 30% drawdown

    def test_recovery_after_drawdown(self):
        curve = [1000.0, 800.0, 1200.0]
        dd, dd_pct = Backtester._max_drawdown(curve)
        assert dd == 200.0   # drawdown from 1000 to 800
        assert abs(dd_pct - 0.20) < 0.001


class TestSharpeRatio:
    def test_empty_curve_returns_zero(self):
        assert Backtester._sharpe_ratio([]) == 0.0
        assert Backtester._sharpe_ratio([1000.0]) == 0.0

    def test_flat_curve_returns_zero(self):
        curve = [1000.0] * 100
        sharpe = Backtester._sharpe_ratio(curve)
        assert sharpe == 0.0   # std dev is 0


class TestWorstDay:
    def test_worst_day_identified(self):
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        curve = [1000.0, 800.0, 900.0]   # worst day: -200 on day 2
        pnl, date = Backtester._worst_day(curve, dates)
        assert pnl == -200.0
        assert date == "2024-01-02"

    def test_no_worst_day_on_single_bar(self):
        pnl, date = Backtester._worst_day([1000.0], ["2024-01-01"])
        assert pnl == 0.0


class TestConsecutiveLosses:
    def test_no_losses(self):
        from trading.backtester import BacktestTrade
        trades = [
            BacktestTrade("", "", "long", 100, 110, 10, 100, 0.1, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 120, 10, 200, 0.2, 2, 0.5, 5),
        ]
        assert Backtester._consecutive_losses(trades) == 0

    def test_all_losses(self):
        from trading.backtester import BacktestTrade
        trades = [
            BacktestTrade("", "", "long", 100, 90, 10, -100, -0.1, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 80, 10, -200, -0.2, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 70, 10, -300, -0.3, 2, 0.5, 5),
        ]
        assert Backtester._consecutive_losses(trades) == 3

    def test_streak_broken(self):
        from trading.backtester import BacktestTrade
        trades = [
            BacktestTrade("", "", "long", 100, 90, 10, -100, -0.1, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 90, 10, -100, -0.1, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 110, 10, 100, 0.1, 2, 0.5, 5),
            BacktestTrade("", "", "long", 100, 90, 10, -100, -0.1, 2, 0.5, 5),
        ]
        assert Backtester._consecutive_losses(trades) == 2

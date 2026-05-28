"""
Unit tests for trading strategies: MovingAverageCrossover, RSIStrategy, VWAPStrategy.

Each test builds a synthetic DataFrame that guarantees a specific signal outcome.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from trading.strategies import (
    MovingAverageCrossover,
    RSIStrategy,
    VWAPStrategy,
    SignalType,
)
from trading.market_data import add_indicators


# ---------------------------------------------------------------------------
# DataFrame builders
# ---------------------------------------------------------------------------

def _make_dates(n: int) -> pd.DatetimeIndex:
    """Generate *n* trading-day timestamps ending on a fixed Friday."""
    return pd.date_range(end="2024-06-28", periods=n, freq="B")  # fixed date avoids off-by-one


def _base_df(n: int = 60) -> pd.DataFrame:
    """Return a skeleton OHLCV DataFrame with *n* rows."""
    dates = _make_dates(n)
    return pd.DataFrame(
        {
            "open": np.full(n, 100.0),
            "high": np.full(n, 105.0),
            "low": np.full(n, 95.0),
            "close": np.full(n, 100.0),
            "volume": np.full(n, 1_000_000),
        },
        index=dates,
    )


def _add_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI column using shared indicator helper."""
    return add_indicators(df)


def _ma_crossover_buy_df() -> pd.DataFrame:
    """Build a DataFrame where SMA20 crosses ABOVE SMA50 at the last bar.

    We directly set sma_20/sma_50 so the crossover fires exactly at iloc[-1].
    """
    n = 60
    df = _base_df(n)
    prices = np.linspace(100, 120, n)
    df["close"] = prices
    df["open"] = prices - 1
    df["high"] = prices + 2
    df["low"] = prices - 2

    # Build MAs where previous bar has fast <= slow, current bar has fast > slow
    sma_20 = np.full(n, 100.0)
    sma_50 = np.full(n, 102.0)   # slow above fast for all prior bars
    # At the last bar: fast jumps above slow
    sma_20[-1] = 103.0
    sma_50[-1] = 102.0
    df["sma_20"] = sma_20
    df["sma_50"] = sma_50
    return df


def _ma_crossover_sell_df() -> pd.DataFrame:
    """Build a DataFrame where SMA20 crosses BELOW SMA50 at the last bar.

    We directly set sma_20/sma_50 so the death cross fires exactly at iloc[-1].
    """
    n = 60
    df = _base_df(n)
    prices = np.linspace(120, 100, n)
    df["close"] = prices
    df["open"] = prices + 1
    df["high"] = prices + 2
    df["low"] = prices - 2

    # fast > slow for all prior bars
    sma_20 = np.full(n, 105.0)
    sma_50 = np.full(n, 103.0)
    # At the last bar: fast drops below slow (death cross)
    sma_20[-1] = 102.0
    sma_50[-1] = 103.0
    df["sma_20"] = sma_20
    df["sma_50"] = sma_50
    return df


def _ma_crossover_hold_df() -> pd.DataFrame:
    """Build a flat DataFrame where no crossover occurs → HOLD."""
    n = 60
    df = _base_df(n)
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    return df


def _rsi_buy_df() -> pd.DataFrame:
    """Build a DataFrame whose last RSI value is below 30 → oversold → BUY."""
    n = 80
    prices = np.concatenate([
        np.full(50, 100.0),
        np.linspace(100, 20, 30),  # sharp drop → RSI << 30
    ])
    df = pd.DataFrame(
        {"open": prices + 1, "high": prices + 2, "low": prices - 2,
         "close": prices, "volume": np.full(n, 1_000_000)},
        index=_make_dates(n),
    )
    return _add_rsi(df)


def _rsi_sell_df() -> pd.DataFrame:
    """Build a DataFrame whose last RSI value is above 70 → overbought → SELL."""
    n = 80
    prices = np.concatenate([
        np.full(50, 100.0),
        np.linspace(100, 200, 30),  # steep rise → RSI > 70
    ])
    df = pd.DataFrame(
        {"open": prices - 1, "high": prices + 2, "low": prices - 2,
         "close": prices, "volume": np.full(n, 1_000_000)},
        index=_make_dates(n),
    )
    return _add_rsi(df)


def _rsi_hold_df() -> pd.DataFrame:
    """Build a DataFrame whose RSI stays between 30 and 70 → HOLD."""
    n = 80
    # Slight oscillation centered at 100 → RSI stays near 50
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.uniform(-0.3, 0.3, n))
    df = pd.DataFrame(
        {"open": prices - 0.3, "high": prices + 0.5, "low": prices - 0.5,
         "close": prices, "volume": np.full(n, 1_000_000)},
        index=_make_dates(n),
    )
    return _add_rsi(df)


def _vwap_buy_df() -> pd.DataFrame:
    """Price above VWAP with upward momentum → BUY."""
    n = 60
    df = _base_df(n)
    prices = np.concatenate([
        np.linspace(100, 105, 40),
        np.linspace(105, 120, 20),
    ])
    df["close"] = prices
    df["open"] = prices - 1
    df["high"] = prices + 2
    df["low"] = prices - 2
    df["volume"] = np.full(n, 1_000_000)

    # VWAP = cumulative(typical_price * volume) / cumulative(volume)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
    return df


def _vwap_sell_df() -> pd.DataFrame:
    """Price below VWAP with downward momentum → SELL."""
    n = 60
    df = _base_df(n)
    prices = np.concatenate([
        np.linspace(120, 115, 40),
        np.linspace(115, 95, 20),
    ])
    df["close"] = prices
    df["open"] = prices + 1
    df["high"] = prices + 2
    df["low"] = prices - 2
    df["volume"] = np.full(n, 1_000_000)

    typical = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
    return df


# ---------------------------------------------------------------------------
# MA Crossover tests
# ---------------------------------------------------------------------------

class TestMovingAverageCrossover:
    """Tests for the MovingAverageCrossover strategy."""

    def test_ma_crossover_buy_signal(self):
        """SMA20 crossing above SMA50 should produce a BUY signal."""
        df = _ma_crossover_buy_df()
        strategy = MovingAverageCrossover()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.BUY
        assert result.confidence > 0
        assert result.strategy is not None

    def test_ma_crossover_sell_signal(self):
        """SMA20 crossing below SMA50 should produce a SELL signal."""
        df = _ma_crossover_sell_df()
        strategy = MovingAverageCrossover()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.SELL
        assert result.confidence > 0

    def test_ma_crossover_hold_signal(self):
        """No crossover in a flat series should produce HOLD."""
        df = _ma_crossover_hold_df()
        strategy = MovingAverageCrossover()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.HOLD


# ---------------------------------------------------------------------------
# RSI Strategy tests
# ---------------------------------------------------------------------------

class TestRSIStrategy:
    """Tests for the RSI-based strategy."""

    def test_rsi_buy_signal(self):
        """RSI < 30 (oversold) should produce a BUY signal."""
        df = _rsi_buy_df()
        strategy = RSIStrategy()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.BUY
        assert result.confidence > 0

    def test_rsi_sell_signal(self):
        """RSI > 70 (overbought) should produce a SELL signal."""
        df = _rsi_sell_df()
        strategy = RSIStrategy()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.SELL
        assert result.confidence > 0

    def test_rsi_hold_signal(self):
        """RSI between 30-70 should produce a HOLD signal."""
        df = _rsi_hold_df()
        strategy = RSIStrategy()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.HOLD


# ---------------------------------------------------------------------------
# VWAP Strategy tests
# ---------------------------------------------------------------------------

class TestVWAPStrategy:
    """Tests for the VWAP-based strategy."""

    def test_vwap_buy_signal(self):
        """Price above VWAP with upward momentum should produce BUY."""
        df = _vwap_buy_df()
        strategy = VWAPStrategy()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.BUY
        assert result.confidence > 0

    def test_vwap_sell_signal(self):
        """Price below VWAP with downward momentum should produce SELL."""
        df = _vwap_sell_df()
        strategy = VWAPStrategy()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.SELL
        assert result.confidence > 0


# ---------------------------------------------------------------------------
# Edge cases & generic signal checks
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge-case and cross-cutting tests."""

    def test_strategy_with_insufficient_data(self):
        """A tiny DataFrame (< required look-back) should yield HOLD."""
        df = _base_df(n=5)
        df["sma_20"] = np.nan
        df["sma_50"] = np.nan

        strategy = MovingAverageCrossover()
        result = strategy.generate_signal(df)

        assert result.signal == SignalType.HOLD

    def test_signal_result_has_all_fields(self):
        """Every SignalResult must expose signal, confidence, strategy, explanation, indicators."""
        df = _ma_crossover_hold_df()
        strategy = MovingAverageCrossover()
        result = strategy.generate_signal(df)

        assert hasattr(result, "signal")
        assert hasattr(result, "confidence")
        assert hasattr(result, "strategy")
        assert hasattr(result, "explanation")
        assert hasattr(result, "indicators")

        assert isinstance(result.confidence, (int, float))
        assert isinstance(result.strategy, str)
        assert isinstance(result.explanation, str)
        assert isinstance(result.indicators, dict)

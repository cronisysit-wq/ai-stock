"""
Trading strategies for signal generation.

Implements three technical-analysis strategies that consume indicator-enriched
DataFrames (produced by `trading.market_data.add_indicators`) and return
structured `SignalResult` objects with confidence scores and plain-English
explanations.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SignalResult:
    """Structured result returned by every strategy."""

    signal: SignalType
    confidence: float  # 0.0 – 1.0
    strategy: str
    explanation: str
    indicators: dict  # key indicator values used for the decision


# ---------------------------------------------------------------------------
# Base strategy
# ---------------------------------------------------------------------------

class BaseStrategy:
    """Abstract base class for all strategies."""

    name: str = "base"

    def generate_signal(self, df: pd.DataFrame) -> SignalResult:
        """Analyse *df* and return a trading signal."""
        raise NotImplementedError

    def _validate_data(self, df: pd.DataFrame, min_rows: int = 50) -> bool:
        """Return ``True`` if *df* has enough rows for analysis."""
        if df is None or df.empty or len(df) < min_rows:
            return False
        return True

    def _hold_signal(self, reason: str, indicators: Optional[dict] = None) -> SignalResult:
        """Convenience helper to return a HOLD signal."""
        return SignalResult(
            signal=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
            explanation=reason,
            indicators=indicators or {},
        )


# ---------------------------------------------------------------------------
# 1. Moving-Average Crossover
# ---------------------------------------------------------------------------

class MovingAverageCrossover(BaseStrategy):
    """
    20 / 50 SMA crossover strategy.

    * **Golden cross** (fast SMA crosses *above* slow SMA) → BUY
    * **Death cross**  (fast SMA crosses *below* slow SMA) → SELL
    * Otherwise → HOLD

    Confidence is proportional to the normalised spread between the two MAs.
    """

    name = "MA Crossover"

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signal(self, df: pd.DataFrame) -> SignalResult:
        if not self._validate_data(df, min_rows=self.slow_period + 2):
            return self._hold_signal(
                f"Insufficient data – need at least {self.slow_period + 2} rows."
            )

        # Use pre-computed columns if available; otherwise compute on the fly.
        fast_col = f"sma_{self.fast_period}"
        slow_col = f"sma_{self.slow_period}"

        if fast_col not in df.columns:
            df = df.copy()
            df[fast_col] = df["close"].rolling(window=self.fast_period).mean()
        if slow_col not in df.columns:
            df = df.copy()
            df[slow_col] = df["close"].rolling(window=self.slow_period).mean()

        # Drop NaN rows created by rolling
        working = df[[fast_col, slow_col, "close"]].dropna()
        if len(working) < 2:
            return self._hold_signal("Not enough computed MA values for crossover detection.")

        fast_prev, fast_curr = working[fast_col].iloc[-2], working[fast_col].iloc[-1]
        slow_prev, slow_curr = working[slow_col].iloc[-2], working[slow_col].iloc[-1]
        close = working["close"].iloc[-1]

        indicators = {
            fast_col: round(float(fast_curr), 4),
            slow_col: round(float(slow_curr), 4),
            "close": round(float(close), 4),
        }

        # Spread-based confidence: |fast – slow| / slow, clamped to [0.1, 1.0]
        spread = abs(fast_curr - slow_curr) / slow_curr if slow_curr != 0 else 0
        confidence = float(np.clip(spread * 20, 0.1, 1.0))  # scale factor 20

        # Golden cross
        if fast_curr > slow_curr and fast_prev <= slow_prev:
            explanation = (
                f"The {self.fast_period}-day SMA (${fast_curr:.2f}) has crossed above the "
                f"{self.slow_period}-day SMA (${slow_curr:.2f}), forming a golden cross. "
                f"This bullish pattern suggests upward momentum is building. "
                f"Current price: ${close:.2f}. Confidence: {confidence:.0%}."
            )
            logger.info("MA Crossover BUY signal – golden cross detected")
            return SignalResult(
                signal=SignalType.BUY,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        # Death cross
        if fast_curr < slow_curr and fast_prev >= slow_prev:
            explanation = (
                f"The {self.fast_period}-day SMA (${fast_curr:.2f}) has crossed below the "
                f"{self.slow_period}-day SMA (${slow_curr:.2f}), forming a death cross. "
                f"This bearish pattern suggests downward momentum is developing. "
                f"Current price: ${close:.2f}. Confidence: {confidence:.0%}."
            )
            logger.info("MA Crossover SELL signal – death cross detected")
            return SignalResult(
                signal=SignalType.SELL,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        # No crossover
        trend = "bullish" if fast_curr > slow_curr else "bearish"
        explanation = (
            f"No crossover detected. The {self.fast_period}-day SMA (${fast_curr:.2f}) is "
            f"{'above' if fast_curr > slow_curr else 'below'} the {self.slow_period}-day SMA "
            f"(${slow_curr:.2f}), indicating a {trend} trend. Current price: ${close:.2f}."
        )
        return SignalResult(
            signal=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
            explanation=explanation,
            indicators=indicators,
        )


# ---------------------------------------------------------------------------
# 2. RSI Strategy
# ---------------------------------------------------------------------------

class RSIStrategy(BaseStrategy):
    """
    Relative Strength Index strategy.

    * RSI < 30  → BUY  (oversold)
    * RSI > 70  → SELL (overbought)
    * Otherwise → HOLD

    Confidence scales with how far RSI is from the neutral 50 zone.
    """

    name = "RSI"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, df: pd.DataFrame) -> SignalResult:
        if not self._validate_data(df, min_rows=self.period + 2):
            return self._hold_signal(
                f"Insufficient data – need at least {self.period + 2} rows."
            )

        # Use pre-computed RSI column if available
        if "rsi" in df.columns:
            rsi_series = df["rsi"].dropna()
        else:
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(window=self.period).mean()
            loss = (-delta.clip(upper=0)).rolling(window=self.period).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi_series = (100 - (100 / (1 + rs))).dropna()

        if rsi_series.empty:
            return self._hold_signal("RSI could not be computed – not enough data.")

        rsi_value = float(rsi_series.iloc[-1])
        close = float(df["close"].iloc[-1])

        indicators = {
            "rsi": round(rsi_value, 2),
            "close": round(close, 4),
            "oversold_threshold": self.oversold,
            "overbought_threshold": self.overbought,
        }

        # Oversold → BUY
        if rsi_value < self.oversold:
            # Confidence: how far below oversold.  RSI 0 → confidence 1.0; RSI 30 → 0.1
            confidence = float(np.clip((self.oversold - rsi_value) / self.oversold, 0.1, 1.0))
            explanation = (
                f"The RSI indicator has dropped to {rsi_value:.1f}, below the oversold "
                f"threshold of {self.oversold:.0f}. This suggests the stock may be oversold "
                f"and could be due for a bounce. Current price: ${close:.2f}. "
                f"Confidence: {confidence:.0%}."
            )
            logger.info("RSI BUY signal – oversold at %.1f", rsi_value)
            return SignalResult(
                signal=SignalType.BUY,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        # Overbought → SELL
        if rsi_value > self.overbought:
            confidence = float(
                np.clip((rsi_value - self.overbought) / (100 - self.overbought), 0.1, 1.0)
            )
            explanation = (
                f"The RSI indicator has risen to {rsi_value:.1f}, above the overbought "
                f"threshold of {self.overbought:.0f}. This suggests the stock may be "
                f"overbought and could face selling pressure. Current price: ${close:.2f}. "
                f"Confidence: {confidence:.0%}."
            )
            logger.info("RSI SELL signal – overbought at %.1f", rsi_value)
            return SignalResult(
                signal=SignalType.SELL,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        # Neutral
        zone = "neutral"
        if rsi_value < 40:
            zone = "slightly bearish"
        elif rsi_value > 60:
            zone = "slightly bullish"

        explanation = (
            f"RSI is at {rsi_value:.1f}, within the neutral range "
            f"({self.oversold:.0f}–{self.overbought:.0f}). "
            f"The momentum is {zone}. Current price: ${close:.2f}. No trade signal."
        )
        return SignalResult(
            signal=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
            explanation=explanation,
            indicators=indicators,
        )


# ---------------------------------------------------------------------------
# 3. VWAP Strategy
# ---------------------------------------------------------------------------

class VWAPStrategy(BaseStrategy):
    """
    Volume-Weighted Average Price strategy.

    * Price *above* VWAP with upward momentum → BUY
    * Price *below* VWAP with downward momentum → SELL
    * Otherwise → HOLD

    Falls back to the 20-day SMA when VWAP is not available.
    """

    name = "VWAP"

    def generate_signal(self, df: pd.DataFrame) -> SignalResult:
        if not self._validate_data(df, min_rows=20):
            return self._hold_signal("Insufficient data – need at least 20 rows.")

        close_curr = float(df["close"].iloc[-1])
        close_prev = float(df["close"].iloc[-2])

        # Determine anchor price: prefer VWAP, fall back to SMA-20
        anchor_label = "VWAP"
        if "vwap" in df.columns and not pd.isna(df["vwap"].iloc[-1]):
            anchor_value = float(df["vwap"].iloc[-1])
        elif "sma_20" in df.columns and not pd.isna(df["sma_20"].iloc[-1]):
            anchor_value = float(df["sma_20"].iloc[-1])
            anchor_label = "SMA-20 (VWAP proxy)"
        else:
            anchor_value = float(df["close"].rolling(20).mean().iloc[-1])
            anchor_label = "20-period mean (VWAP proxy)"

        indicators = {
            "close": round(close_curr, 4),
            "prev_close": round(close_prev, 4),
            anchor_label: round(anchor_value, 4),
        }

        price_above = close_curr > anchor_value
        momentum_up = close_curr > close_prev
        price_below = close_curr < anchor_value
        momentum_down = close_curr < close_prev

        # Confidence based on distance from anchor
        distance_pct = abs(close_curr - anchor_value) / anchor_value if anchor_value != 0 else 0
        confidence = float(np.clip(distance_pct * 25, 0.1, 1.0))

        if price_above and momentum_up:
            explanation = (
                f"Price (${close_curr:.2f}) is trading above {anchor_label} "
                f"(${anchor_value:.2f}) with upward momentum (previous close: "
                f"${close_prev:.2f}). This suggests bullish pressure and institutional "
                f"buying interest. Confidence: {confidence:.0%}."
            )
            logger.info("VWAP BUY signal – price above %s with upward momentum", anchor_label)
            return SignalResult(
                signal=SignalType.BUY,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        if price_below and momentum_down:
            explanation = (
                f"Price (${close_curr:.2f}) is trading below {anchor_label} "
                f"(${anchor_value:.2f}) with downward momentum (previous close: "
                f"${close_prev:.2f}). This suggests bearish pressure and potential "
                f"distribution. Confidence: {confidence:.0%}."
            )
            logger.info("VWAP SELL signal – price below %s with downward momentum", anchor_label)
            return SignalResult(
                signal=SignalType.SELL,
                confidence=confidence,
                strategy=self.name,
                explanation=explanation,
                indicators=indicators,
            )

        # Mixed signals
        if price_above:
            bias = "above"
            note = "but momentum is flat or negative – wait for confirmation"
        elif price_below:
            bias = "below"
            note = "but momentum is flat or positive – wait for confirmation"
        else:
            bias = "at"
            note = "no clear directional bias"

        explanation = (
            f"Price (${close_curr:.2f}) is {bias} {anchor_label} "
            f"(${anchor_value:.2f}), {note}. Current close: ${close_curr:.2f}, "
            f"previous close: ${close_prev:.2f}."
        )
        return SignalResult(
            signal=SignalType.HOLD,
            confidence=0.0,
            strategy=self.name,
            explanation=explanation,
            indicators=indicators,
        )


# ---------------------------------------------------------------------------
# Registry & helper functions
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY = {
    "MA Crossover": MovingAverageCrossover,
    "RSI": RSIStrategy,
    "VWAP": VWAPStrategy,
}


def get_strategy(name: str) -> BaseStrategy:
    """Return a strategy instance by *name*; defaults to MA Crossover."""
    strategies = {
        "MA Crossover": MovingAverageCrossover(),
        "RSI": RSIStrategy(),
        "VWAP": VWAPStrategy(),
    }
    return strategies.get(name, MovingAverageCrossover())


def get_all_strategies() -> list:
    """Return a list of all available strategy instances."""
    return [MovingAverageCrossover(), RSIStrategy(), VWAPStrategy()]

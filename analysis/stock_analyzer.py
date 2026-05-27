"""
Stock Analysis Engine.

Analyzes a single ticker using technical indicators and produces a
structured StockAnalysis result. This module ONLY analyzes — it does
not place orders or override the risk manager.

Safety
------
* This module never places orders.
* All signals are labeled as educational analysis only.
* Disclaimer appended to all reason_summary fields.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    " | ⚠️ Not financial advice. Educational analysis only. "
    "Past indicators do not guarantee future results."
)

# Valid signal values
SIGNAL_BUY_CANDIDATE = "BUY_CANDIDATE"
SIGNAL_SELL_CANDIDATE = "SELL_CANDIDATE"
SIGNAL_WATCH = "WATCH"
SIGNAL_AVOID = "AVOID"

VALID_SIGNALS = {SIGNAL_BUY_CANDIDATE, SIGNAL_SELL_CANDIDATE, SIGNAL_WATCH, SIGNAL_AVOID}


@dataclass
class StockAnalysis:
    """Complete analysis result for a single ticker."""
    ticker: str
    current_price: float
    signal: str                  # BUY_CANDIDATE | SELL_CANDIDATE | WATCH | AVOID
    confidence: float            # 0–100
    risk_score: float            # 0–100 (higher = riskier)
    trend_score: float           # 0–100
    momentum_score: float        # 0–100
    volume_score: float          # 0–100
    overall_score: float         # 0–100 weighted composite
    stop_loss_price: float
    take_profit_price: float
    support_level: float
    resistance_level: float
    reason_summary: str
    indicators: Dict[str, Any] = field(default_factory=dict)
    timeframe_bias: str = "swing"   # short_term | swing | long_term
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    portfolio_note: str = ""        # hold/reduce/add/avoid_adding
    error: Optional[str] = None


class StockAnalyzer:
    """
    Analyzes a stock ticker using technical indicators.

    Parameters
    ----------
    stop_loss_pct : float
        Stop-loss percentage below entry (e.g. 2.0 = 2%).
    take_profit_pct : float
        Take-profit percentage above entry (e.g. 5.0 = 5%).
    """

    def __init__(
        self,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 5.0,
    ) -> None:
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        ticker: str,
        current_positions: Optional[Dict[str, float]] = None,
        max_allocation_pct: float = 20.0,
        portfolio_value: float = 0.0,
    ) -> StockAnalysis:
        """
        Analyze a single ticker and return StockAnalysis.

        Parameters
        ----------
        ticker :
            Stock symbol (e.g. 'AAPL').
        current_positions :
            Dict mapping ticker → current market value in USD.
        max_allocation_pct :
            Max % of portfolio in one ticker before flagging over-concentration.
        portfolio_value :
            Total portfolio value in USD (used for allocation check).
        """
        ticker = ticker.strip().upper()
        try:
            df = self._fetch_data(ticker)
            if df is None or df.empty or len(df) < 30:
                return self._error_result(ticker, "Insufficient historical data")

            df = self._compute_indicators(df)
            scores = self._compute_scores(df)
            price = float(df["close"].iloc[-1])
            price_source = "daily_close"

            try:
                from trading.market_data import get_live_quote
                quote = get_live_quote(ticker)
                if quote.get("price") and float(quote["price"]) > 0:
                    price = float(quote["price"])
                    price_source = quote.get("source", "live")
            except Exception:
                pass

            signal, confidence = self._determine_signal(scores)
            timeframe = self._determine_timeframe(df, scores)
            reason = self._build_reason(ticker, signal, scores, df)
            portfolio_note = self._portfolio_note(
                ticker, price, current_positions or {}, max_allocation_pct, portfolio_value
            )

            stop_loss = round(price * (1 - self.stop_loss_pct / 100), 2)
            take_profit = round(price * (1 + self.take_profit_pct / 100), 2)
            support = round(float(df["low"].tail(20).min()), 2)
            resistance = round(float(df["high"].tail(20).max()), 2)

            indicators = self._extract_indicators(df)
            indicators["price_source"] = price_source

            return StockAnalysis(
                ticker=ticker,
                current_price=price,
                signal=signal,
                confidence=confidence,
                risk_score=scores["risk_score"],
                trend_score=scores["trend_score"],
                momentum_score=scores["momentum_score"],
                volume_score=scores["volume_score"],
                overall_score=scores["overall_score"],
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                support_level=support,
                resistance_level=resistance,
                reason_summary=reason + _DISCLAIMER,
                indicators=indicators,
                timeframe_bias=timeframe,
                timestamp=datetime.now(timezone.utc),
                portfolio_note=portfolio_note,
            )
        except Exception as exc:
            logger.error("StockAnalyzer error for %s: %s", ticker, exc)
            return self._error_result(ticker, str(exc))

    # ── Data Fetching ─────────────────────────────────────────────────────────

    def _fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch 90 days of OHLCV data from yfinance."""
        try:
            raw = yf.download(ticker, period="90d", interval="1d", progress=False, auto_adjust=True)
            if raw is None or raw.empty:
                return None
            # Normalize column names to lowercase
            df = raw.copy()
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df.rename(columns={"vol": "volume"})  # safety
            df = df.dropna(subset=["close"])
            return df
        except Exception as exc:
            logger.warning("yfinance fetch failed for %s: %s", ticker, exc)
            return None

    # ── Indicator Computation ─────────────────────────────────────────────────

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to the DataFrame."""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # SMAs
        df["sma_20"] = close.rolling(20).mean()
        df["sma_50"] = close.rolling(50).mean() if len(df) >= 50 else pd.Series(np.nan, index=df.index)
        df["sma_200"] = close.rolling(200).mean() if len(df) >= 200 else pd.Series(np.nan, index=df.index)

        # RSI (14)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands (20, 2)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["bb_upper"] = bb_mid + 2 * bb_std
        df["bb_lower"] = bb_mid - 2 * bb_std
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

        # ATR (14)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()
        df["atr_pct"] = df["atr"] / close * 100  # ATR as % of price

        # VWAP (rolling daily approximation)
        typical_price = (high + low + close) / 3
        df["vwap"] = (typical_price * volume).rolling(20).sum() / volume.rolling(20).sum()

        # Volume trend
        df["vol_ma20"] = volume.rolling(20).mean()
        df["vol_ratio"] = volume / df["vol_ma20"]

        # Rate of change (momentum)
        df["roc_5"] = close.pct_change(5) * 100
        df["roc_21"] = close.pct_change(21) * 100

        # Max drawdown (21-day rolling)
        rolling_max = close.rolling(21).max()
        df["drawdown_pct"] = (close - rolling_max) / rolling_max * 100

        return df

    # ── Score Computation ─────────────────────────────────────────────────────

    def _compute_scores(self, df: pd.DataFrame) -> Dict[str, float]:
        """Compute all component scores (0-100) from the last row of indicators."""
        row = df.iloc[-1]
        close = float(row["close"])

        # ── Trend Score (SMA alignment, MACD) ────────────────────────────────
        trend = 50.0
        sma20 = row.get("sma_20")
        sma50 = row.get("sma_50")
        sma200 = row.get("sma_200")
        macd_hist = row.get("macd_hist")
        vwap = row.get("vwap")

        if pd.notna(sma20) and close > sma20:
            trend += 10
        if pd.notna(sma50) and close > sma50:
            trend += 10
        if pd.notna(sma200) and close > sma200:
            trend += 10
        if pd.notna(sma20) and pd.notna(sma50) and sma20 > sma50:
            trend += 8
        if pd.notna(macd_hist) and macd_hist > 0:
            trend += 8
        if pd.notna(vwap) and close > vwap:
            trend += 4
        trend = min(100.0, max(0.0, trend))

        # ── Momentum Score (RSI, ROC) ─────────────────────────────────────────
        momentum = 50.0
        rsi = row.get("rsi")
        roc5 = row.get("roc_5")
        roc21 = row.get("roc_21")

        if pd.notna(rsi):
            if 50 < rsi <= 70:
                momentum += 20   # bullish momentum
            elif rsi > 70:
                momentum += 5    # overbought — weaker
            elif rsi < 30:
                momentum -= 20   # oversold
            elif 30 <= rsi <= 45:
                momentum -= 5    # weak
        if pd.notna(roc5):
            momentum += min(15, max(-15, roc5 * 3))  # scale ROC contribution
        if pd.notna(roc21):
            momentum += min(10, max(-10, roc21 * 1))
        momentum = min(100.0, max(0.0, momentum))

        # ── Volume Score ──────────────────────────────────────────────────────
        volume_score = 50.0
        vol_ratio = row.get("vol_ratio")
        if pd.notna(vol_ratio):
            if vol_ratio > 1.5:
                volume_score = 80.0
            elif vol_ratio > 1.2:
                volume_score = 65.0
            elif vol_ratio < 0.7:
                volume_score = 30.0
            elif vol_ratio < 0.5:
                volume_score = 15.0
        volume_score = min(100.0, max(0.0, volume_score))

        # ── Risk Score (ATR%, drawdown, BBand width) — higher = riskier ──────
        risk = 30.0  # baseline
        atr_pct = row.get("atr_pct")
        drawdown = row.get("drawdown_pct")
        bb_width = row.get("bb_width")

        if pd.notna(atr_pct):
            risk += min(30, atr_pct * 5)  # 6% ATR = +30 risk points
        if pd.notna(drawdown):
            risk += min(20, abs(float(drawdown)) * 2)
        if pd.notna(bb_width):
            risk += min(20, float(bb_width) * 50)  # wide bands = more risk
        risk = min(100.0, max(0.0, risk))

        # ── Overall Score (weighted composite) ────────────────────────────────
        overall = (
            trend * 0.35
            + momentum * 0.25
            + volume_score * 0.15
            + (100 - risk) * 0.25
        )
        overall = min(100.0, max(0.0, overall))

        return {
            "trend_score": round(trend, 1),
            "momentum_score": round(momentum, 1),
            "volume_score": round(volume_score, 1),
            "risk_score": round(risk, 1),
            "overall_score": round(overall, 1),
        }

    # ── Signal Determination ──────────────────────────────────────────────────

    def _determine_signal(self, scores: Dict[str, float]) -> tuple[str, float]:
        """Map scores to a signal and confidence value."""
        overall = scores["overall_score"]
        risk = scores["risk_score"]
        momentum = scores["momentum_score"]

        if overall >= 65 and risk < 55:
            signal = SIGNAL_BUY_CANDIDATE
            confidence = min(100, overall + (55 - risk) * 0.3)
        elif overall <= 35 or risk > 75:
            signal = SIGNAL_AVOID
            confidence = min(100, (100 - overall) + risk * 0.2)
        elif overall >= 50 and risk >= 55:
            signal = SIGNAL_WATCH
            confidence = overall * 0.7
        elif momentum < 40:
            signal = SIGNAL_SELL_CANDIDATE
            confidence = min(100, (100 - momentum) * 0.8)
        else:
            signal = SIGNAL_WATCH
            confidence = 50.0

        return signal, round(min(100.0, max(0.0, confidence)), 1)

    # ── Timeframe Bias ────────────────────────────────────────────────────────

    def _determine_timeframe(self, df: pd.DataFrame, scores: Dict[str, float]) -> str:
        """Estimate whether signal is short-term, swing, or long-term oriented."""
        row = df.iloc[-1]
        rsi = row.get("rsi", 50)
        roc5 = row.get("roc_5", 0)
        sma200 = row.get("sma_200")
        close = float(row["close"])

        if pd.notna(sma200) and close > float(sma200) and scores["trend_score"] > 65:
            return "long_term"
        elif abs(float(roc5)) > 3 or (pd.notna(rsi) and (float(rsi) > 70 or float(rsi) < 30)):
            return "short_term"
        else:
            return "swing"

    # ── Reason Summary ────────────────────────────────────────────────────────

    def _build_reason(self, ticker: str, signal: str, scores: Dict[str, float], df: pd.DataFrame) -> str:
        """Build a human-readable reason summary from indicators."""
        row = df.iloc[-1]
        parts = [f"{ticker} — {signal}:"]

        # Trend
        sma20 = row.get("sma_20")
        sma50 = row.get("sma_50")
        close = float(row["close"])
        if pd.notna(sma20):
            rel = "above" if close > float(sma20) else "below"
            parts.append(f"Price is {rel} SMA(20) (${float(sma20):.2f}).")
        if pd.notna(sma50):
            rel = "above" if close > float(sma50) else "below"
            parts.append(f"Price is {rel} SMA(50) (${float(sma50):.2f}).")

        # RSI
        rsi = row.get("rsi")
        if pd.notna(rsi):
            zone = "overbought" if float(rsi) > 70 else ("oversold" if float(rsi) < 30 else "neutral")
            parts.append(f"RSI(14) is {float(rsi):.1f} ({zone}).")

        # MACD
        macd_hist = row.get("macd_hist")
        if pd.notna(macd_hist):
            direction = "positive (bullish)" if float(macd_hist) > 0 else "negative (bearish)"
            parts.append(f"MACD histogram is {direction}.")

        # Volume
        vol_ratio = row.get("vol_ratio")
        if pd.notna(vol_ratio):
            vol_desc = "above" if float(vol_ratio) > 1.0 else "below"
            parts.append(f"Volume is {float(vol_ratio):.1f}x 20-day average ({vol_desc} average).")

        parts.append(f"Scores — Trend:{scores['trend_score']:.0f} Momentum:{scores['momentum_score']:.0f} Risk:{scores['risk_score']:.0f} Overall:{scores['overall_score']:.0f}/100.")

        return " ".join(parts)

    # ── Portfolio Note ────────────────────────────────────────────────────────

    def _portfolio_note(
        self,
        ticker: str,
        price: float,
        current_positions: Dict[str, float],
        max_allocation_pct: float,
        portfolio_value: float,
    ) -> str:
        """Generate a portfolio-aware note if the ticker is already held."""
        if ticker not in current_positions or portfolio_value <= 0:
            return ""

        current_value = current_positions[ticker]
        allocation_pct = (current_value / portfolio_value) * 100

        if allocation_pct >= max_allocation_pct:
            return f"AVOID_ADDING — already at {allocation_pct:.1f}% of portfolio (limit: {max_allocation_pct:.0f}%)"
        elif allocation_pct >= max_allocation_pct * 0.75:
            return f"REDUCE — at {allocation_pct:.1f}% of portfolio, approaching limit of {max_allocation_pct:.0f}%"
        else:
            return f"HOLD — currently {allocation_pct:.1f}% of portfolio (limit: {max_allocation_pct:.0f}%)"

    # ── Indicator Extract ─────────────────────────────────────────────────────

    def _extract_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract key indicator values from last row for display."""
        row = df.iloc[-1]
        result = {}
        for col in ["rsi", "macd", "macd_signal", "macd_hist", "sma_20", "sma_50",
                    "sma_200", "atr", "atr_pct", "vwap", "bb_upper", "bb_lower",
                    "bb_width", "vol_ratio", "roc_5", "roc_21", "drawdown_pct"]:
            val = row.get(col)
            if pd.notna(val):
                result[col] = round(float(val), 4)
        return result

    # ── Error Result ──────────────────────────────────────────────────────────

    def _error_result(self, ticker: str, error: str) -> StockAnalysis:
        """Return a safe error result when analysis cannot complete."""
        return StockAnalysis(
            ticker=ticker,
            current_price=0.0,
            signal=SIGNAL_AVOID,
            confidence=0.0,
            risk_score=100.0,
            trend_score=0.0,
            momentum_score=0.0,
            volume_score=0.0,
            overall_score=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            support_level=0.0,
            resistance_level=0.0,
            reason_summary=f"Analysis failed for {ticker}: {error}{_DISCLAIMER}",
            error=error,
        )

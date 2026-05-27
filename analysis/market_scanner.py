"""
Market Scanner — finds the best day-trading and swing-trading candidates
from a large universe of stocks automatically.

How it works
------------
1. Takes a preset universe (day_trading = ~150, sp500 = ~400, all = ~650).
2. Fetches 5-day intraday + 60-day daily data for every ticker in parallel.
3. Scores each ticker on 8 day-trading specific signals.
4. Returns top N ranked candidates sorted best → worst.

Signal Dimensions (day-trading focus)
--------------------------------------
* Volume Surge      — today's volume vs. 20-day average
* Price Momentum    — % move in last 1, 3, 5 days
* Intraday Range    — ATR-based volatility opportunity
* RSI Zone          — oversold bounce (30-45) or momentum (55-70)
* MACD Cross        — bullish/bearish crossover signal
* Gap Analysis      — pre-market gap-up (breakout setup)
* Relative Strength — vs. SPY/QQQ on same day
* Trend Alignment   — price vs. 20/50-day SMA

NOT FINANCIAL ADVICE. Scores are algorithmic only.
"""

from __future__ import annotations

import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from analysis.universe import get_universe

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n⚠️ Scanner output is NOT financial advice. "
    "Day trading involves significant risk of loss. "
    "Past indicator patterns do not predict future results. "
    "Paper trade first. Never risk money you can't afford to lose."
)

# ── Presets ────────────────────────────────────────────────────────────────────
SCAN_PRESETS = {
    "🔥 Day Trading Hot List":  "day_trading",
    "📈 S&P 500 Movers":        "sp500",
    "💻 Tech Sector":           "sector:technology",
    "⚡ EV & Clean Energy":      "sector:ev_clean",
    "🧬 Biotech":               "sector:biotech",
    "🪙 Crypto-Adjacent":        "sector:crypto_adj",
    "💰 Financials":             "sector:financials",
    "🏥 Healthcare":            "sector:healthcare",
    "🛢️ Energy":                "sector:energy",
    "📦 Consumer":              "sector:consumer",
    "🌍 Full Universe":          "all",
}

# ── Score weights ──────────────────────────────────────────────────────────────
WEIGHTS = {
    "volume_surge":     0.22,
    "price_momentum":   0.20,
    "rsi_zone":         0.15,
    "macd_signal":      0.13,
    "trend_alignment":  0.12,
    "intraday_range":   0.10,
    "gap_score":        0.05,
    "rel_strength":     0.03,
}


@dataclass
class ScanResult:
    """Result for a single ticker from the market scan."""
    ticker: str
    rank: int = 0
    price: float = 0.0
    change_pct_1d: float = 0.0
    change_pct_5d: float = 0.0
    volume: int = 0
    avg_volume: int = 0
    volume_ratio: float = 0.0          # today / 20d avg
    rsi: float = 0.0
    macd_hist: float = 0.0
    atr_pct: float = 0.0               # ATR as % of price
    gap_pct: float = 0.0               # open vs prev close %
    # Component scores (0-100)
    volume_score: float = 0.0
    momentum_score: float = 0.0
    rsi_score: float = 0.0
    macd_score: float = 0.0
    trend_score: float = 0.0
    range_score: float = 0.0
    gap_score: float = 0.0
    rel_strength_score: float = 0.0
    overall_score: float = 0.0
    signal: str = "WATCH"              # BUY_CANDIDATE | WATCH | AVOID
    confidence: float = 0.0
    action: str = "Watchlist"
    explanation: str = ""
    error: str = ""
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_valid(self) -> bool:
        return not self.error and self.price > 0


@dataclass
class ScanSession:
    """Complete output of one market scan."""
    session_id: str
    preset: str
    universe_size: int
    scanned: int
    results: List[ScanResult]
    top_n: int
    elapsed_seconds: float = 0.0
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = field(default=_DISCLAIMER)

    @property
    def top(self) -> Optional[ScanResult]:
        return self.results[0] if self.results else None

    @property
    def as_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self.results:
            action_color = r.action
            rows.append({
                "Rank":         r.rank,
                "Ticker":       r.ticker,
                "Price":        f"${r.price:,.2f}",
                "1D Change":    f"{r.change_pct_1d:+.2f}%",
                "5D Change":    f"{r.change_pct_5d:+.2f}%",
                "Volume Ratio": f"{r.volume_ratio:.1f}x",
                "RSI":          f"{r.rsi:.1f}",
                "ATR %":        f"{r.atr_pct:.2f}%",
                "Gap %":        f"{r.gap_pct:+.2f}%",
                "Signal":       r.signal,
                "Confidence":   f"{r.confidence:.0f}",
                "Score":        f"{r.overall_score:.1f}",
                "Action":       r.action,
                "Stop Loss":    f"${r.stop_loss_price:,.2f}",
                "Take Profit":  f"${r.take_profit_price:,.2f}",
            })
        return pd.DataFrame(rows)


class MarketScanner:
    """
    Scans a universe of stocks and returns the best day-trading candidates.

    Parameters
    ----------
    max_workers : int
        Parallel fetch threads (default 20 — safe for yfinance rate limits).
    min_price : float
        Skip stocks below this price (default $2 — avoids penny stocks).
    min_avg_volume : int
        Skip stocks with < this 20d avg daily volume (default 500K).
    top_n : int
        Return only the top N ranked results.
    stop_loss_pct : float
        Stop-loss % for suggested levels.
    take_profit_pct : float
        Take-profit % for suggested levels.
    """

    def __init__(
        self,
        max_workers: int = 20,
        min_price: float = 2.0,
        min_avg_volume: int = 500_000,
        top_n: int = 30,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 4.0,
    ) -> None:
        self.max_workers = max_workers
        self.min_price = min_price
        self.min_avg_volume = min_avg_volume
        self.top_n = top_n
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def scan(self, preset: str = "day_trading", progress_callback=None) -> ScanSession:
        """
        Run a full market scan on the chosen preset universe.

        Parameters
        ----------
        preset : str
            Universe preset key (e.g. "day_trading", "sp500", "all").
        progress_callback : callable, optional
            Called with (completed, total) as each ticker finishes.

        Returns
        -------
        ScanSession with top_n ranked ScanResult objects.
        """
        import time
        t0 = time.time()
        session_id = str(uuid.uuid4())

        universe = get_universe(preset)
        total = len(universe)
        logger.info("MarketScanner: scanning %d tickers (preset=%s)", total, preset)

        # Fetch SPY data for relative strength baseline
        spy_change = self._get_spy_change()

        results: List[ScanResult] = []
        completed_count = [0]

        with ThreadPoolExecutor(max_workers=min(self.max_workers, total)) as pool:
            futures = {pool.submit(self._scan_ticker, ticker, spy_change): ticker for ticker in universe}
            for future in as_completed(futures):
                completed_count[0] += 1
                if progress_callback:
                    try:
                        progress_callback(completed_count[0], total)
                    except Exception:
                        pass
                try:
                    res = future.result(timeout=30)
                    if res is not None:
                        results.append(res)
                except Exception as exc:
                    ticker = futures[future]
                    logger.debug("Scan failed for %s: %s", ticker, exc)

        # Filter: min price + min volume
        filtered = [
            r for r in results
            if r.is_valid
            and r.price >= self.min_price
            and r.avg_volume >= self.min_avg_volume
        ]

        # Sort by overall_score descending
        sorted_results = sorted(filtered, key=lambda r: r.overall_score, reverse=True)

        # Take top N and assign ranks
        top_results = sorted_results[:self.top_n]
        for i, r in enumerate(top_results, start=1):
            r.rank = i

        elapsed = round(time.time() - t0, 2)
        logger.info(
            "MarketScanner done: %d/%d valid, top %d selected in %.1fs",
            len(filtered), total, len(top_results), elapsed,
        )

        return ScanSession(
            session_id=session_id,
            preset=preset,
            universe_size=total,
            scanned=len(results),
            results=top_results,
            top_n=self.top_n,
            elapsed_seconds=elapsed,
        )

    # ── Per-ticker analysis ────────────────────────────────────────────────────

    def _scan_ticker(self, ticker: str, spy_change: float) -> Optional[ScanResult]:
        """Fetch and score a single ticker. Returns None on hard failure."""
        try:
            result = ScanResult(ticker=ticker)
            tkr = yf.Ticker(ticker)

            # Fetch 60 days of daily data
            hist = tkr.history(period="60d", interval="1d", auto_adjust=True)
            if hist.empty or len(hist) < 10:
                result.error = "Insufficient data"
                return result

            close = hist["Close"]
            volume = hist["Volume"]
            high = hist["High"]
            low = hist["Low"]
            open_ = hist["Open"]

            latest_close = float(close.iloc[-1])
            if latest_close <= 0:
                result.error = "Invalid price"
                return result

            result.price = latest_close
            result.volume = int(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0

            # ── 1. Volume surge ────────────────────────────────────────────────
            avg_vol = float(volume.iloc[:-1].rolling(20).mean().iloc[-1]) if len(volume) > 20 else float(volume.mean())
            result.avg_volume = int(avg_vol) if not math.isnan(avg_vol) and avg_vol > 0 else 0
            if avg_vol > 0 and result.volume > 0:
                vol_ratio = result.volume / avg_vol
            else:
                vol_ratio = 1.0
            result.volume_ratio = round(vol_ratio, 2)
            # Score: 3x+ = 100, 2x = 70, 1.5x = 45, 1x = 20
            result.volume_score = min(100.0, max(0.0, (vol_ratio - 1.0) / 2.0 * 100))

            # ── 2. Price momentum ──────────────────────────────────────────────
            prev1 = float(close.iloc[-2]) if len(close) >= 2 else latest_close
            prev5 = float(close.iloc[-6]) if len(close) >= 6 else float(close.iloc[0])

            chg1 = (latest_close - prev1) / prev1 * 100 if prev1 > 0 else 0.0
            chg5 = (latest_close - prev5) / prev5 * 100 if prev5 > 0 else 0.0
            result.change_pct_1d = round(chg1, 3)
            result.change_pct_5d = round(chg5, 3)

            # Combined momentum score
            mom_raw = (chg1 * 0.6 + chg5 * 0.4)
            result.momentum_score = min(100.0, max(0.0, 50.0 + mom_raw * 4))

            # ── 3. RSI (14-day) ───────────────────────────────────────────────
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, 0.0001)
            rsi_series = 100 - (100 / (1 + rs))
            rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0
            result.rsi = round(rsi, 2)

            # Day trading: oversold bounce 30-45 = great entry, momentum 55-70 = continuation
            if 30 <= rsi <= 45:
                result.rsi_score = 90.0   # oversold bounce setup
            elif 45 < rsi <= 60:
                result.rsi_score = 65.0   # neutral / weak momentum
            elif 60 < rsi <= 72:
                result.rsi_score = 80.0   # momentum continuation
            elif rsi < 30:
                result.rsi_score = 55.0   # oversold but may keep falling
            else:
                result.rsi_score = 30.0   # overbought — risky entry

            # ── 4. MACD ───────────────────────────────────────────────────────
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_hist = macd_line - signal_line

            hist_val = float(macd_hist.iloc[-1]) if not pd.isna(macd_hist.iloc[-1]) else 0.0
            hist_prev = float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else 0.0
            result.macd_hist = round(hist_val, 4)

            if hist_val > 0 and hist_val > hist_prev:
                result.macd_score = 85.0   # bullish and accelerating
            elif hist_val > 0:
                result.macd_score = 65.0   # bullish but slowing
            elif hist_val < 0 and hist_val < hist_prev:
                result.macd_score = 20.0   # bearish and accelerating down
            else:
                result.macd_score = 40.0   # bearish but recovering

            # ── 5. Trend alignment (SMA 20/50) ────────────────────────────────
            sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else latest_close
            sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else latest_close

            above_20 = latest_close > sma20
            above_50 = latest_close > sma50
            sma20_above_50 = sma20 > sma50

            if above_20 and above_50 and sma20_above_50:
                result.trend_score = 90.0
            elif above_20 and above_50:
                result.trend_score = 75.0
            elif above_20:
                result.trend_score = 55.0
            elif above_50:
                result.trend_score = 40.0
            else:
                result.trend_score = 20.0

            # ── 6. Intraday range / ATR (volatility opportunity) ───────────────
            true_ranges = []
            for i in range(1, min(15, len(hist))):
                tr = max(
                    float(high.iloc[-i]) - float(low.iloc[-i]),
                    abs(float(high.iloc[-i]) - float(close.iloc[-i-1])),
                    abs(float(low.iloc[-i]) - float(close.iloc[-i-1])),
                )
                true_ranges.append(tr)
            atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
            atr_pct = (atr / latest_close * 100) if latest_close > 0 else 0.0
            result.atr_pct = round(atr_pct, 3)

            # Day trading: sweet spot is 1.5%-4% ATR (enough range, not too wild)
            if 1.5 <= atr_pct <= 4.0:
                result.range_score = 85.0
            elif 0.8 <= atr_pct < 1.5:
                result.range_score = 55.0   # not much range
            elif 4.0 < atr_pct <= 7.0:
                result.range_score = 65.0   # high volatility — profitable but risky
            elif atr_pct > 7.0:
                result.range_score = 40.0   # too volatile — hard to manage
            else:
                result.range_score = 25.0   # too flat

            # ── 7. Gap analysis (today open vs. prev close) ────────────────────
            today_open = float(open_.iloc[-1]) if not pd.isna(open_.iloc[-1]) else latest_close
            prev_close = float(close.iloc[-2]) if len(close) >= 2 else latest_close
            gap_pct = (today_open - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
            result.gap_pct = round(gap_pct, 3)

            if gap_pct >= 1.5:
                result.gap_score = 85.0   # gap-up = momentum setup
            elif gap_pct >= 0.5:
                result.gap_score = 65.0
            elif gap_pct <= -1.5:
                result.gap_score = 30.0   # gap-down = caution
            elif gap_pct <= -0.5:
                result.gap_score = 40.0
            else:
                result.gap_score = 50.0   # flat open

            # ── 8. Relative strength vs. SPY ──────────────────────────────────
            rel = chg1 - spy_change
            result.rel_strength_score = min(100.0, max(0.0, 50.0 + rel * 5))

            # ── Overall weighted score ─────────────────────────────────────────
            overall = (
                WEIGHTS["volume_surge"]    * result.volume_score +
                WEIGHTS["price_momentum"]  * result.momentum_score +
                WEIGHTS["rsi_zone"]        * result.rsi_score +
                WEIGHTS["macd_signal"]     * result.macd_score +
                WEIGHTS["trend_alignment"] * result.trend_score +
                WEIGHTS["intraday_range"]  * result.range_score +
                WEIGHTS["gap_score"]       * result.gap_score +
                WEIGHTS["rel_strength"]    * result.rel_strength_score
            )
            result.overall_score = round(overall, 2)

            # ── Signal classification ──────────────────────────────────────────
            if overall >= 68 and result.volume_ratio >= 1.3:
                result.signal = "BUY_CANDIDATE"
                result.confidence = min(95.0, overall)
                result.action = "Consider (not financial advice)"
            elif overall >= 55:
                result.signal = "WATCH"
                result.confidence = overall * 0.85
                result.action = "Watchlist candidate"
            else:
                result.signal = "AVOID"
                result.confidence = 100 - overall
                result.action = "Avoid or monitor"

            # ── Stop-loss / take-profit (rule engine) ─────────────────────────
            result.stop_loss_price = round(latest_close * (1 - self.stop_loss_pct / 100), 2)
            result.take_profit_price = round(latest_close * (1 + self.take_profit_pct / 100), 2)

            # ── Explanation ───────────────────────────────────────────────────
            result.explanation = self._build_explanation(result)

            return result

        except Exception as exc:
            logger.debug("_scan_ticker %s error: %s", ticker, exc)
            return ScanResult(ticker=ticker, error=str(exc)[:120])

    def _get_spy_change(self) -> float:
        """Get SPY 1-day change for relative strength calculation."""
        try:
            spy = yf.Ticker("SPY").history(period="5d", interval="1d")
            if len(spy) >= 2:
                c = spy["Close"]
                return float((c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100)
        except Exception:
            pass
        return 0.0

    def _build_explanation(self, r: ScanResult) -> str:
        """Build a 2-3 sentence educational explanation."""
        parts = []

        # Volume
        if r.volume_ratio >= 2.0:
            parts.append(f"Volume is {r.volume_ratio:.1f}x above average — significant unusual activity.")
        elif r.volume_ratio >= 1.3:
            parts.append(f"Volume is {r.volume_ratio:.1f}x average — above-normal participation.")

        # Price momentum
        if r.change_pct_1d >= 2.0:
            parts.append(f"Up {r.change_pct_1d:.2f}% today with {r.change_pct_5d:+.2f}% over 5 days — bullish momentum.")
        elif r.change_pct_1d <= -2.0:
            parts.append(f"Down {r.change_pct_1d:.2f}% today — potential reversal setup or continued weakness.")

        # RSI
        if 30 <= r.rsi <= 45:
            parts.append(f"RSI {r.rsi:.0f} — oversold zone, possible bounce setup (not a guarantee).")
        elif 60 < r.rsi <= 72:
            parts.append(f"RSI {r.rsi:.0f} — momentum zone, trend continuation pattern.")
        elif r.rsi > 75:
            parts.append(f"RSI {r.rsi:.0f} — overbought, higher risk entry point.")

        # Gap
        if r.gap_pct >= 1.5:
            parts.append(f"Gapped up {r.gap_pct:.2f}% at open — breakout candidate.")
        elif r.gap_pct <= -1.5:
            parts.append(f"Gapped down {r.gap_pct:.2f}% — watch for continuation or reversal.")

        # ATR
        parts.append(
            f"ATR {r.atr_pct:.1f}% suggests "
            f"{'good intraday range for day trading' if 1.5 <= r.atr_pct <= 4.0 else 'limited' if r.atr_pct < 1.5 else 'high volatility — size positions carefully'}."
            f" Overall technical score: {r.overall_score:.0f}/100."
            f" ⚠️ Not financial advice."
        )

        return " ".join(parts[:4])

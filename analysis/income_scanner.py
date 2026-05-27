"""
Income / Swing Scanner — finds US stocks suited for swing trades and
steady monthly-style gains (not day-trading volatility).

Scans large-cap US universe (S&P 500) for:
  - Strong trend alignment (SMA stack)
  - Moderate risk (lower ATR% preferred)
  - Positive momentum without extreme overbought RSI
  - Liquidity (volume vs 20-day average)

Estimates educational daily $ potential using ATR-based position sizing
toward a user-defined daily target ($100–$200 default range).

NOT FINANCIAL ADVICE. Estimates are illustrative only.
"""

from __future__ import annotations

import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from analysis.stock_analyzer import StockAnalyzer, SIGNAL_BUY_CANDIDATE, SIGNAL_WATCH
from analysis.universe import get_universe
from trading.position_sizer import PositionSizer

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n⚠️ Income estimates are NOT guarantees. "
    "Swing trading involves risk of loss. "
    "Daily $100–$200 targets require capital, volatility, and favorable moves — "
    "often NOT achievable consistently. Educational analysis only."
)

INCOME_PRESETS = {
    "💎 S&P 500 Quality": "sp500",
    "📈 NASDAQ Growth": "nasdaq100",
    "🏦 Dividend & Financials": "sector:financials",
    "💻 Tech Leaders": "sector:technology",
    "🏥 Healthcare": "sector:healthcare",
}


@dataclass
class IncomeScanResult:
    """Single ticker result from income/swing scan."""
    ticker: str
    rank: int = 0
    price: float = 0.0
    signal: str = "WATCH"
    confidence: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    risk_score: float = 0.0
    volume_score: float = 0.0
    overall_score: float = 0.0
    income_score: float = 0.0          # re-weighted for swing/income
    atr_pct: float = 0.0
    atr_dollars: float = 0.0           # avg daily range in $
    change_pct_5d: float = 0.0
    change_pct_21d: float = 0.0
    vol_ratio: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    timeframe_bias: str = "swing"
    suggested_shares: float = 0.0
    est_daily_potential: float = 0.0   # shares × ATR (1 full range move)
    est_daily_conservative: float = 0.0  # 30% of ATR move
    meets_daily_target: bool = False
    explanation: str = ""
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error and self.price > 0


@dataclass
class IncomeScanSession:
    """Complete income scan output."""
    session_id: str
    preset: str
    universe_size: int
    scanned: int
    results: List[IncomeScanResult]
    top_n: int
    daily_target_usd: float
    account_equity: float
    elapsed_seconds: float = 0.0
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = field(default=_DISCLAIMER)

    @property
    def top(self) -> Optional[IncomeScanResult]:
        return self.results[0] if self.results else None

    @property
    def as_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self.results:
            rows.append({
                "Rank": r.rank,
                "Ticker": r.ticker,
                "Price": f"${r.price:,.2f}",
                "Signal": r.signal,
                "Income Score": f"{r.income_score:.1f}",
                "Trend": f"{r.trend_score:.0f}",
                "Risk": f"{r.risk_score:.0f}",
                "5D Chg": f"{r.change_pct_5d:+.2f}%",
                "21D Chg": f"{r.change_pct_21d:+.2f}%",
                "ATR/day": f"${r.atr_dollars:.2f}",
                "Est. Daily ($)": f"${r.est_daily_conservative:,.0f}",
                "Meets Target": "✅" if r.meets_daily_target else "—",
                "Shares": f"{r.suggested_shares:.0f}",
                "Stop Loss": f"${r.stop_loss_price:,.2f}",
                "Take Profit": f"${r.take_profit_price:,.2f}",
                "Timeframe": r.timeframe_bias.replace("_", " ").title(),
            })
        return pd.DataFrame(rows)


class IncomeScanner:
    """
    Scans US large-cap universe for swing / monthly-income style candidates.

    Parameters
    ----------
    max_workers : int
        Parallel analysis threads.
    min_price : float
        Skip penny/low-priced names.
    min_income_score : float
        Minimum income score to include in results.
    top_n : int
        Number of results to return.
    """

    def __init__(
        self,
        max_workers: int = 10,
        min_price: float = 15.0,
        min_income_score: float = 55.0,
        top_n: int = 25,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 5.0,
    ) -> None:
        self.max_workers = max_workers
        self.min_price = min_price
        self.min_income_score = min_income_score
        self.top_n = top_n
        self.analyzer = StockAnalyzer(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        self.sizer = PositionSizer()

    def scan(
        self,
        preset: str = "sp500",
        daily_target_usd: float = 150.0,
        account_equity: float = 25_000.0,
        progress_callback=None,
    ) -> IncomeScanSession:
        """Run income scan across preset universe."""
        import time
        t0 = time.time()
        session_id = str(uuid.uuid4())
        universe = get_universe(preset)
        total = len(universe)
        logger.info("IncomeScanner: scanning %d tickers (preset=%s)", total, preset)

        results: List[IncomeScanResult] = []
        completed = [0]

        with ThreadPoolExecutor(max_workers=min(self.max_workers, total)) as pool:
            futures = {
                pool.submit(
                    self._analyze_ticker,
                    ticker,
                    daily_target_usd,
                    account_equity,
                ): ticker
                for ticker in universe
            }
            for future in as_completed(futures):
                completed[0] += 1
                if progress_callback:
                    try:
                        progress_callback(completed[0], total)
                    except Exception:
                        pass
                try:
                    res = future.result(timeout=45)
                    if res is not None:
                        results.append(res)
                except Exception as exc:
                    ticker = futures[future]
                    logger.debug("Income scan failed for %s: %s", ticker, exc)

        filtered = [
            r for r in results
            if r.is_valid
            and r.price >= self.min_price
            and r.income_score >= self.min_income_score
            and r.signal in (SIGNAL_BUY_CANDIDATE, SIGNAL_WATCH)
        ]
        sorted_results = sorted(filtered, key=lambda r: r.income_score, reverse=True)
        top = sorted_results[: self.top_n]
        for i, r in enumerate(top, start=1):
            r.rank = i

        elapsed = round(time.time() - t0, 2)
        return IncomeScanSession(
            session_id=session_id,
            preset=preset,
            universe_size=total,
            scanned=len(results),
            results=top,
            top_n=self.top_n,
            daily_target_usd=daily_target_usd,
            account_equity=account_equity,
            elapsed_seconds=elapsed,
        )

    def _analyze_ticker(
        self,
        ticker: str,
        daily_target_usd: float,
        account_equity: float,
    ) -> Optional[IncomeScanResult]:
        """Analyze one ticker for income suitability."""
        try:
            analysis = self.analyzer.analyze(ticker)
            if analysis.error or analysis.current_price <= 0:
                return IncomeScanResult(
                    ticker=ticker,
                    error=analysis.error or "Invalid price",
                )

            ind = analysis.indicators
            atr_pct = float(ind.get("atr_pct", 0) or 0)
            atr_dollars = float(ind.get("atr", 0) or 0)
            if atr_dollars <= 0 and atr_pct > 0:
                atr_dollars = analysis.current_price * atr_pct / 100

            vol_ratio = float(ind.get("vol_ratio", 1.0) or 1.0)
            roc5 = float(ind.get("roc_5", 0) or 0)
            roc21 = float(ind.get("roc_21", 0) or 0)

            # Income score: favor trend + low risk + steady momentum
            income_score = (
                analysis.trend_score * 0.35
                + (100 - analysis.risk_score) * 0.30
                + analysis.momentum_score * 0.20
                + analysis.volume_score * 0.15
            )
            # Penalize extreme overbought
            rsi = ind.get("rsi")
            if rsi is not None and float(rsi) > 75:
                income_score -= 15
            income_score = max(0.0, min(100.0, income_score))

            sizing = self.sizer.calculate(
                current_price=analysis.current_price,
                account_equity=account_equity,
                stop_loss_price=analysis.stop_loss_price,
                atr_pct=atr_pct if atr_pct else None,
                take_profit_price=analysis.take_profit_price,
            )
            shares = sizing.suggested_qty

            est_daily = shares * atr_dollars if atr_dollars > 0 else 0.0
            est_conservative = est_daily * 0.30  # ~30% of avg daily range
            meets_target = est_conservative >= daily_target_usd * 0.5

            explanation = self._build_explanation(
                analysis.ticker, income_score, analysis, atr_dollars,
                est_conservative, daily_target_usd,
            )

            return IncomeScanResult(
                ticker=analysis.ticker,
                price=analysis.current_price,
                signal=analysis.signal,
                confidence=analysis.confidence,
                trend_score=analysis.trend_score,
                momentum_score=analysis.momentum_score,
                risk_score=analysis.risk_score,
                volume_score=analysis.volume_score,
                overall_score=analysis.overall_score,
                income_score=round(income_score, 2),
                atr_pct=round(atr_pct, 3),
                atr_dollars=round(atr_dollars, 2),
                change_pct_5d=round(roc5, 2),
                change_pct_21d=round(roc21, 2),
                vol_ratio=round(vol_ratio, 2),
                stop_loss_price=analysis.stop_loss_price,
                take_profit_price=analysis.take_profit_price,
                timeframe_bias=analysis.timeframe_bias,
                suggested_shares=shares,
                est_daily_potential=round(est_daily, 2),
                est_daily_conservative=round(est_conservative, 2),
                meets_daily_target=meets_target,
                explanation=explanation,
            )
        except Exception as exc:
            return IncomeScanResult(ticker=ticker, error=str(exc)[:120])

    @staticmethod
    def _build_explanation(
        ticker: str,
        income_score: float,
        analysis,
        atr_dollars: float,
        est_conservative: float,
        daily_target: float,
    ) -> str:
        parts = [
            f"{ticker} income score {income_score:.0f}/100 — "
            f"trend {analysis.trend_score:.0f}, risk {analysis.risk_score:.0f}.",
        ]
        if atr_dollars > 0:
            parts.append(
                f"Avg daily range ~${atr_dollars:.2f}/share; "
                f"conservative est. ~${est_conservative:,.0f}/day at suggested size "
                f"(NOT a guarantee). Target reference: ${daily_target:,.0f}/day."
            )
        parts.append(
            f"Signal: {analysis.signal}. Swing/monthly bias — educational only."
        )
        return " ".join(parts)

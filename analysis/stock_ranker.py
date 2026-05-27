"""
Stock Ranker — ranks a list of tickers by overall quality score.

This module compares stocks across multiple dimensions and produces a
prioritized ranking. All output is educational only.

Safety
------
* Rankings are NOT trading recommendations.
* No orders are placed by this module.
* Mandatory disclaimer included in all output.
"""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from analysis.stock_analyzer import StockAnalysis, StockAnalyzer, SIGNAL_BUY_CANDIDATE, SIGNAL_AVOID, SIGNAL_SELL_CANDIDATE
from db.database import get_db_session
from db.models import StockRanking

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n⚠️ Rankings are based on technical indicators only and are for "
    "educational purposes. They do not constitute financial advice, "
    "investment recommendations, or profit guarantees. "
    "Always consult a qualified financial advisor."
)


@dataclass
class RankedStock:
    """A single ticker in the ranked output."""
    rank: int
    analysis: StockAnalysis
    suggested_action: str    # 'Consider (not financial advice)' | 'Watchlist candidate' | 'Avoid or monitor'
    explanation: str         # 2-3 sentence non-actionable summary

    @property
    def ticker(self) -> str:
        return self.analysis.ticker

    @property
    def price(self) -> float:
        return self.analysis.current_price

    @property
    def signal(self) -> str:
        return self.analysis.signal

    @property
    def confidence(self) -> float:
        return self.analysis.confidence

    @property
    def risk_score(self) -> float:
        return self.analysis.risk_score

    @property
    def overall_score(self) -> float:
        return self.analysis.overall_score


@dataclass
class RankingResult:
    """Complete output of a ranking session."""
    session_id: str
    ranked: List[RankedStock]
    tickers_input: List[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = field(default=_DISCLAIMER)

    @property
    def top(self) -> Optional[RankedStock]:
        return self.ranked[0] if self.ranked else None

    @property
    def as_dict_list(self) -> List[dict]:
        """Convert to list of dicts for Streamlit display."""
        rows = []
        for r in self.ranked:
            rows.append({
                "Rank": r.rank,
                "Ticker": r.ticker,
                "Price": f"${r.price:,.2f}",
                "Signal": r.signal,
                "Confidence": f"{r.confidence:.0f}",
                "Risk": f"{r.risk_score:.0f}",
                "Trend": f"{r.analysis.trend_score:.0f}",
                "Momentum": f"{r.analysis.momentum_score:.0f}",
                "Overall Score": f"{r.overall_score:.0f}",
                "Action": r.suggested_action,
                "Timeframe": r.analysis.timeframe_bias.replace("_", " ").title(),
                "Stop Loss": f"${r.analysis.stop_loss_price:,.2f}",
                "Take Profit": f"${r.analysis.take_profit_price:,.2f}",
                "Explanation": r.explanation,
            })
        return rows


class StockRanker:
    """
    Ranks a list of tickers by multi-factor scoring.

    Parameters
    ----------
    max_workers:
        Number of parallel yfinance fetches (default 5).
    stop_loss_pct:
        Passed through to StockAnalyzer.
    take_profit_pct:
        Passed through to StockAnalyzer.
    """

    def __init__(
        self,
        max_workers: int = 5,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 5.0,
    ) -> None:
        self.max_workers = max_workers
        self.analyzer = StockAnalyzer(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

    def rank(
        self,
        tickers: List[str],
        current_positions: Optional[Dict[str, float]] = None,
        max_allocation_pct: float = 20.0,
        portfolio_value: float = 0.0,
    ) -> RankingResult:
        """
        Rank a list of tickers by overall score.

        Parameters
        ----------
        tickers:
            List of stock symbols to analyze and rank.
        current_positions:
            Dict of ticker → position market value (for portfolio-aware notes).
        max_allocation_pct:
            Concentration cap per ticker.
        portfolio_value:
            Total portfolio value in USD.

        Returns
        -------
        RankingResult with ranked list ordered best-to-worst.
        """
        tickers = [t.strip().upper() for t in tickers if t.strip()]
        if not tickers:
            return RankingResult(
                session_id=str(uuid.uuid4()),
                ranked=[],
                tickers_input=[],
            )

        session_id = str(uuid.uuid4())
        analyses: Dict[str, StockAnalysis] = {}

        # Parallel fetch + analyze
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(tickers))) as pool:
            futures = {
                pool.submit(
                    self.analyzer.analyze, ticker, current_positions, max_allocation_pct, portfolio_value
                ): ticker
                for ticker in tickers
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    analyses[ticker] = future.result()
                except Exception as exc:
                    logger.error("Analysis failed for %s: %s", ticker, exc)

        # Sort by overall_score descending (errors go to bottom)
        sorted_analyses = sorted(
            analyses.values(),
            key=lambda a: (0 if a.error else 1, a.overall_score),
            reverse=True,
        )

        ranked = []
        for i, analysis in enumerate(sorted_analyses, start=1):
            action = self._suggested_action(analysis)
            explanation = self._build_explanation(analysis, i, sorted_analyses)
            ranked.append(RankedStock(
                rank=i,
                analysis=analysis,
                suggested_action=action,
                explanation=explanation,
            ))

        result = RankingResult(
            session_id=session_id,
            ranked=ranked,
            tickers_input=tickers,
        )

        self._persist(result)
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _suggested_action(self, analysis: StockAnalysis) -> str:
        """Map signal + confidence to a non-actionable suggested action label."""
        if analysis.error:
            return "Data unavailable"
        if analysis.signal == SIGNAL_BUY_CANDIDATE and analysis.confidence >= 60:
            return "Consider (not financial advice)"
        elif analysis.signal == SIGNAL_BUY_CANDIDATE:
            return "Watchlist candidate"
        elif analysis.signal == SIGNAL_AVOID or analysis.signal == SIGNAL_SELL_CANDIDATE:
            return "Avoid or monitor for exit"
        else:
            return "Watchlist candidate"

    def _build_explanation(self, analysis: StockAnalysis, rank: int, all_analyses: list) -> str:
        """Build a 2-3 sentence non-actionable educational explanation."""
        if analysis.error:
            return f"Analysis could not be completed for {analysis.ticker}: {analysis.error}"

        parts = []
        a = analysis

        # Rank context
        if rank == 1:
            parts.append(
                f"{a.ticker} is the higher-ranked candidate based on a combined technical score of {a.overall_score:.0f}/100."
            )
        else:
            top = all_analyses[0] if all_analyses else None
            if top and top.ticker != a.ticker:
                diff = top.overall_score - a.overall_score
                parts.append(
                    f"{a.ticker} scores {a.overall_score:.0f}/100, which is {diff:.0f} points below "
                    f"the top-ranked candidate ({top.ticker}) based on technical indicators."
                )
            else:
                parts.append(f"{a.ticker} technical score: {a.overall_score:.0f}/100.")

        # Key strengths or weaknesses
        strengths = []
        if a.trend_score >= 65:
            strengths.append(f"strong trend ({a.trend_score:.0f})")
        if a.momentum_score >= 65:
            strengths.append(f"positive momentum ({a.momentum_score:.0f})")
        if a.volume_score >= 65:
            strengths.append(f"above-average volume ({a.volume_score:.0f})")
        weaknesses = []
        if a.risk_score >= 60:
            weaknesses.append(f"elevated risk ({a.risk_score:.0f})")
        if a.trend_score < 40:
            weaknesses.append(f"weak trend ({a.trend_score:.0f})")
        if a.momentum_score < 40:
            weaknesses.append(f"low momentum ({a.momentum_score:.0f})")

        if strengths:
            parts.append(f"Technical strengths: {', '.join(strengths)}.")
        if weaknesses:
            parts.append(f"Risk factors: {', '.join(weaknesses)}.")

        # Timeframe
        tf = a.timeframe_bias.replace("_", "-")
        parts.append(f"Indicator bias suggests {tf} timeframe. This is educational analysis only, not a trade recommendation.")

        return " ".join(parts)

    def _persist(self, result: RankingResult) -> None:
        """Persist ranking session to DB for audit trail."""
        try:
            db = get_db_session()
            ranked_json = json.dumps([
                {
                    "rank": r.rank,
                    "ticker": r.ticker,
                    "signal": r.signal,
                    "overall_score": r.overall_score,
                    "confidence": r.confidence,
                    "risk_score": r.risk_score,
                    "action": r.suggested_action,
                }
                for r in result.ranked
            ])
            record = StockRanking(
                session_id=result.session_id,
                tickers_input=",".join(result.tickers_input),
                ranked_results_json=ranked_json,
                top_ticker=result.top.ticker if result.top else None,
                created_at=result.timestamp,
            )
            db.add(record)
            db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to persist ranking: %s", exc)

"""
US Market Sentiment Scanner — broad US equity sentiment sweep.

Mimics how professional trading desks monitor the market:
  - Scan large US universes (S&P 500, NASDAQ, day-trading list, full)
  - Rank by composite sentiment (news + analysts + momentum + sector)
  - Sector breadth breakdown
  - Market-wide bullish/bearish breadth
  - Top sentiment movers (momentum shifts)

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from analysis.sentiment_analyzer import SentimentAnalyzer, SentimentResult
from analysis.universe import get_universe, SECTORS

logger = logging.getLogger(__name__)

US_SENTIMENT_PRESETS = {
    "🟢 Robinhood All (~8,000+)": "robinhood",
    "📈 Robinhood Stocks": "robinhood_stocks",
    "💎 S&P 500": "sp500_full",
    "🔥 Day Trading (fast)": "day_trading",
    "💻 Technology": "sector:technology",
    "🏦 Financials": "sector:financials",
    "🏥 Healthcare": "sector:healthcare",
    "🛢️ Energy": "sector:energy",
    "📦 Consumer": "sector:consumer",
    "🧬 Biotech": "sector:biotech",
}


@dataclass
class USSentimentRow:
    """Single ticker sentiment snapshot for US scan."""
    ticker: str
    rank: int = 0
    price: float = 0.0
    sector: str = "unknown"
    industry: str = "N/A"
    overall_score: float = 50.0
    news_score: float = 50.0
    analyst_score: float = 50.0
    sentiment_label: str = "NEUTRAL"
    sentiment_momentum: float = 0.0
    earnings_tone: str = "NEUTRAL"
    social_buzz: float = 50.0
    analyst_recommendation: str = "N/A"
    price_vs_target_pct: float = 0.0
    bullish_headlines: int = 0
    bearish_headlines: int = 0
    catalyst_notes: str = ""
    market_trend: str = "NEUTRAL"
    raw: Optional[SentimentResult] = None
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error and self.price > 0


@dataclass
class SectorBreadth:
    sector: str
    count: int
    avg_sentiment: float
    bullish_pct: float
    top_ticker: str = ""


@dataclass
class USMarketSentimentSession:
    """Complete US-wide sentiment scan output."""
    session_id: str
    preset: str
    universe_size: int
    scanned: int
    results: List[USSentimentRow]
    sector_breadth: List[SectorBreadth] = field(default_factory=list)
    market_bullish_pct: float = 0.0
    market_bearish_pct: float = 0.0
    market_neutral_pct: float = 0.0
    avg_sentiment: float = 50.0
    top_momentum: List[USSentimentRow] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = (
        "⚠️ US sentiment scan is educational only. Data is lagged from Yahoo Finance. "
        "NOT FINANCIAL ADVICE."
    )


class USMarketSentimentScanner:
    """
    Parallel US sentiment scanner — how real desks sweep the market for news/sentiment.
    """

    def __init__(
        self,
        max_workers: int = 12,
        min_score: float = 0.0,
        top_n: int = 50,
    ) -> None:
        self.max_workers = max_workers
        self.min_score = min_score
        self.top_n = top_n
        self.analyzer = SentimentAnalyzer(max_news=15)

    def scan(
        self,
        preset: str = "sp500",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        limit: Optional[int] = None,
    ) -> USMarketSentimentSession:
        """Scan US universe and rank by sentiment."""
        session_id = str(uuid.uuid4())[:8]
        tickers = get_universe(preset)
        if limit and limit > 0:
            tickers = tickers[:limit]
        total = len(tickers)
        t0 = time.time()
        rows: List[USSentimentRow] = []
        done = [0]

        def _analyze(ticker: str) -> USSentimentRow:
            try:
                sent = self.analyzer.analyze(ticker)
                price = 0.0
                if sent.is_valid:
                    try:
                        import yfinance as yf
                        info = yf.Ticker(ticker).info or {}
                        price = float(
                            info.get("currentPrice")
                            or info.get("regularMarketPrice")
                            or 0
                        )
                    except Exception:
                        pass
                return USSentimentRow(
                    ticker=ticker.upper(),
                    price=price,
                    sector=sent.sector,
                    industry=sent.industry,
                    overall_score=sent.overall_sentiment_score,
                    news_score=sent.news_sentiment_score,
                    analyst_score=sent.analyst_score,
                    sentiment_label=sent.overall_sentiment_label,
                    sentiment_momentum=sent.sentiment_momentum,
                    earnings_tone=sent.earnings_tone,
                    social_buzz=sent.social_buzz_score,
                    analyst_recommendation=sent.analyst_recommendation,
                    price_vs_target_pct=sent.price_vs_target_pct,
                    bullish_headlines=sent.bullish_headlines,
                    bearish_headlines=sent.bearish_headlines,
                    catalyst_notes=sent.catalyst_notes,
                    market_trend=sent.market_trend,
                    raw=sent if sent.is_valid else None,
                    error=sent.error,
                )
            except Exception as exc:
                return USSentimentRow(ticker=ticker.upper(), error=str(exc)[:120])

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, total))) as pool:
            futures = {pool.submit(_analyze, t): t for t in tickers}
            for future in as_completed(futures):
                done[0] += 1
                if progress_callback:
                    try:
                        progress_callback(done[0], total)
                    except Exception:
                        pass
                try:
                    row = future.result(timeout=45)
                    if row.is_valid and row.overall_score >= self.min_score:
                        rows.append(row)
                except Exception as exc:
                    ticker = futures[future]
                    logger.debug("US sentiment scan failed %s: %s", ticker, exc)

        rows.sort(key=lambda r: r.overall_score, reverse=True)
        top = rows[: self.top_n]
        for i, r in enumerate(top, start=1):
            r.rank = i

        sector_breadth = self._compute_sector_breadth(rows)
        bull_pct, bear_pct, neut_pct = self._market_breadth(rows)
        avg = sum(r.overall_score for r in rows) / len(rows) if rows else 50.0
        momentum = sorted(rows, key=lambda r: r.sentiment_momentum, reverse=True)[:10]

        return USMarketSentimentSession(
            session_id=session_id,
            preset=preset,
            universe_size=total,
            scanned=len(rows),
            results=top,
            sector_breadth=sector_breadth,
            market_bullish_pct=bull_pct,
            market_bearish_pct=bear_pct,
            market_neutral_pct=neut_pct,
            avg_sentiment=round(avg, 1),
            top_momentum=momentum,
            elapsed_seconds=round(time.time() - t0, 2),
        )

    def _compute_sector_breadth(self, rows: List[USSentimentRow]) -> List[SectorBreadth]:
        by_sector: Dict[str, List[USSentimentRow]] = {}
        for r in rows:
            by_sector.setdefault(r.sector, []).append(r)

        breadth = []
        for sector, items in sorted(by_sector.items(), key=lambda x: -len(x[1])):
            if sector == "unknown" and len(items) < 2:
                continue
            bullish = sum(1 for i in items if i.sentiment_label == "BULLISH")
            avg = sum(i.overall_score for i in items) / len(items)
            top = max(items, key=lambda x: x.overall_score)
            breadth.append(SectorBreadth(
                sector=sector,
                count=len(items),
                avg_sentiment=round(avg, 1),
                bullish_pct=round(bullish / len(items) * 100, 1),
                top_ticker=top.ticker,
            ))
        return sorted(breadth, key=lambda b: b.avg_sentiment, reverse=True)

    @staticmethod
    def _market_breadth(rows: List[USSentimentRow]) -> tuple[float, float, float]:
        if not rows:
            return 0.0, 0.0, 0.0
        n = len(rows)
        bull = sum(1 for r in rows if r.sentiment_label == "BULLISH")
        bear = sum(1 for r in rows if r.sentiment_label == "BEARISH")
        neut = n - bull - bear
        return round(bull / n * 100, 1), round(bear / n * 100, 1), round(neut / n * 100, 1)

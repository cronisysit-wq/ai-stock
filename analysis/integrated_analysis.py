"""
Integrated Analysis — merges technical scan, news sentiment, and fundamentals
into a single composite score for ranking and AI advisory.

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analysis.sentiment_analyzer import SentimentAnalyzer, SentimentResult, NewsItem

logger = logging.getLogger(__name__)


@dataclass
class IntegratedAnalysis:
    """Full picture: technical + sentiment + news for one ticker."""
    ticker: str
    price: float
    technical_score: float
    sentiment_score: float
    news_score: float
    composite_score: float
    signal: str
    volume_ratio: float = 0.0
    atr_pct: float = 0.0
    explanation: str = ""
    sentiment: Optional[SentimentResult] = None
    news_headlines: List[NewsItem] = field(default_factory=list)
    sentiment_label: str = "NEUTRAL"
    analyst_consensus: str = "N/A"
    catalyst_notes: str = ""
    sector: str = "unknown"
    industry: str = "N/A"
    earnings_tone: str = "NEUTRAL"
    sentiment_momentum: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def top_headlines(self) -> List[str]:
        return [n.title for n in self.news_headlines[:5]]


def compute_composite_score(
    technical_score: float,
    sentiment_score: float,
    news_score: Optional[float] = None,
    technical_weight: float = 0.50,
    sentiment_weight: float = 0.30,
    news_weight: float = 0.20,
) -> float:
    """Weighted composite 0–100."""
    ns = news_score if news_score is not None else sentiment_score
    total_w = technical_weight + sentiment_weight + news_weight
    composite = (
        technical_score * technical_weight
        + sentiment_score * sentiment_weight
        + ns * news_weight
    ) / total_w
    return round(min(100.0, max(0.0, composite)), 2)


class IntegratedAnalyzer:
    """
    Enriches scanner/ranker results with live news + sentiment from Yahoo Finance.
    """

    def __init__(self, max_workers: int = 8) -> None:
        self.sentiment = SentimentAnalyzer(max_news=12)
        self.max_workers = max_workers

    def analyze_ticker(
        self,
        ticker: str,
        price: float,
        technical_score: float,
        signal: str = "WATCH",
        explanation: str = "",
        volume_ratio: float = 0.0,
        atr_pct: float = 0.0,
        technical_weight: float = 0.50,
        sentiment_weight: float = 0.30,
        news_weight: float = 0.20,
    ) -> IntegratedAnalysis:
        """Single-ticker integrated analysis."""
        sent = self.sentiment.analyze(ticker, current_price=price)
        news_score = sent.news_sentiment_score if sent.is_valid else 50.0
        composite = compute_composite_score(
            technical_score, sent.overall_sentiment_score, news_score,
            technical_weight, sentiment_weight, news_weight,
        )
        return IntegratedAnalysis(
            ticker=ticker.upper(),
            price=price,
            technical_score=technical_score,
            sentiment_score=sent.overall_sentiment_score if sent.is_valid else 50.0,
            news_score=news_score,
            composite_score=composite,
            signal=signal,
            volume_ratio=volume_ratio,
            atr_pct=atr_pct,
            explanation=explanation,
            sentiment=sent if sent.is_valid else None,
            news_headlines=sent.news_items[:8] if sent.is_valid else [],
            sentiment_label=sent.overall_sentiment_label if sent.is_valid else "NEUTRAL",
            analyst_consensus=sent.analyst_recommendation if sent.is_valid else "N/A",
            catalyst_notes=sent.catalyst_notes if sent.is_valid else "",
            sector=sent.sector if sent.is_valid else "unknown",
            industry=sent.industry if sent.is_valid else "N/A",
            earnings_tone=sent.earnings_tone if sent.is_valid else "NEUTRAL",
            sentiment_momentum=sent.sentiment_momentum if sent.is_valid else 0.0,
        )

    def enrich_batch(
        self,
        items: List[Dict[str, Any]],
        technical_weight: float = 0.50,
        sentiment_weight: float = 0.30,
        news_weight: float = 0.20,
        progress_callback=None,
    ) -> List[IntegratedAnalysis]:
        """
        Parallel sentiment enrichment for a list of dicts with keys:
        ticker, price, technical_score, signal, explanation, volume_ratio, atr_pct
        """
        results: List[IntegratedAnalysis] = []
        total = len(items)
        done = [0]

        def _one(item: Dict[str, Any]) -> IntegratedAnalysis:
            return self.analyze_ticker(
                ticker=item["ticker"],
                price=item["price"],
                technical_score=item["technical_score"],
                signal=item.get("signal", "WATCH"),
                explanation=item.get("explanation", ""),
                volume_ratio=item.get("volume_ratio", 0.0),
                atr_pct=item.get("atr_pct", 0.0),
                technical_weight=technical_weight,
                sentiment_weight=sentiment_weight,
                news_weight=news_weight,
            )

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, total))) as pool:
            futures = {pool.submit(_one, item): item for item in items}
            for future in as_completed(futures):
                done[0] += 1
                if progress_callback:
                    try:
                        progress_callback(done[0], total)
                    except Exception:
                        pass
                try:
                    results.append(future.result(timeout=30))
                except Exception as exc:
                    item = futures[future]
                    logger.debug("Integrated analysis failed %s: %s", item.get("ticker"), exc)

        results.sort(key=lambda r: r.composite_score, reverse=True)
        return results

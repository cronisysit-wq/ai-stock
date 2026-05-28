"""
Strategy + Sentiment Scanner — ranks ALL stocks by technical strategy + sentiment.

Every stock gets:
  - Strategy signal & score (StockAnalyzer technicals)
  - Sentiment score (news + analysts + momentum)
  - Composite rank → suggested action (STRONG BUY / INVEST / WATCH / AVOID)
  - Live or near-live price when available
  - Plain-English "why" summary

Designed for Robinhood-scale US universes (8,000+ symbols via NASDAQ Trader directory).

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

from analysis.integrated_analysis import compute_composite_score
from analysis.sentiment_analyzer import SentimentAnalyzer
from analysis.stock_analyzer import StockAnalyzer, SIGNAL_BUY_CANDIDATE, SIGNAL_WATCH
from analysis.universe import get_universe, price_in_range, resolve_scan_universe

logger = logging.getLogger(__name__)

SCAN_PRESETS = {
    "🟢 Robinhood All (~8,000+)": "robinhood",
    "📈 Robinhood Stocks (no ETFs)": "robinhood_stocks",
    "💎 S&P 500 Full": "sp500_full",
    "📊 S&P 500 Curated": "sp500",
    "🔥 Day Trading (fast)": "day_trading",
    "💰 Penny stocks (< $5)": "penny_under_5",
    "🪙 True pennies (< $1)": "penny_under_1",
    "💵 $1 – $10 range": "price_1_10",
    "📉 Under $10": "under_10",
}

ACTION_STRONG_BUY = "STRONG BUY"
ACTION_INVEST = "INVEST"
ACTION_WATCH = "WATCH"
ACTION_AVOID = "AVOID"

_ACTION_SORT_ORDER = {
    ACTION_STRONG_BUY: 0,
    ACTION_INVEST: 1,
    ACTION_WATCH: 2,
    ACTION_AVOID: 3,
}

_ANALYST_SORT_ORDER = {
    "STRONG BUY": 0,
    "BUY": 1,
    "HOLD": 2,
    "SELL": 3,
    "STRONG SELL": 4,
    "N/A": 5,
}


@dataclass
class StrategySentimentRow:
    """One stock: strategy + sentiment + suggested action."""
    ticker: str
    rank: int = 0
    price: float = 0.0
    price_source: str = "daily_close"
    price_as_of: str = ""
    strategy_signal: str = "WATCH"
    strategy_score: float = 0.0
    sentiment_score: float = 50.0
    news_score: float = 50.0
    sentiment_label: str = "NEUTRAL"
    composite_score: float = 50.0
    suggested_action: str = ACTION_WATCH
    why: str = ""
    analyst: str = "N/A"
    sector: str = "unknown"
    stop_loss: float = 0.0
    take_profit: float = 0.0
    sentiment_momentum: float = 0.0
    earnings_tone: str = "NEUTRAL"
    ai_note: str = ""
    ai_powered: bool = False
    ai_provider: str = ""
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error and self.price > 0

    @property
    def price_label(self) -> str:
        src = (self.price_source or "daily_close").replace("_", " ")
        if self.price_source in ("live", "market", "intraday"):
            return f"live ({src})"
        return f"delayed ({src})"


@dataclass
class StrategySentimentSession:
    session_id: str
    preset: str
    universe_size: int
    scanned: int
    results: List[StrategySentimentRow]
    elapsed_seconds: float = 0.0
    ai_scan_provider: str = ""
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = (
        "⚠️ NOT FINANCIAL ADVICE. Suggested actions are algorithmic (strategy + sentiment). "
        "Not guaranteed. Paper trade first."
    )

    @property
    def invest_count(self) -> int:
        return sum(1 for r in self.results if r.suggested_action == ACTION_INVEST)

    @property
    def strong_buy_count(self) -> int:
        return sum(1 for r in self.results if r.suggested_action == ACTION_STRONG_BUY)

    @property
    def ai_notes_count(self) -> int:
        return sum(1 for r in self.results if r.ai_note)


def _normalize_analyst(analyst: str) -> str:
    a = (analyst or "N/A").upper().strip()
    if "STRONG" in a and "BUY" in a:
        return "STRONG BUY"
    if "STRONG" in a and "SELL" in a:
        return "STRONG SELL"
    if a in ("BUY", "HOLD", "SELL", "N/A"):
        return a if a != "N/A" else analyst or "N/A"
    return analyst or "N/A"


def _suggested_action(
    composite: float,
    strategy_signal: str,
    sentiment_label: str,
    sentiment_score: float,
    analyst: str = "N/A",
) -> str:
    """Classify row — STRONG BUY is top tier (always sorted first)."""
    analyst_norm = _normalize_analyst(analyst)

    if strategy_signal == "AVOID" or (sentiment_label == "BEARISH" and sentiment_score < 40):
        return ACTION_AVOID

    strong_buy = (
        analyst_norm == "STRONG BUY"
        and composite >= 65
        and strategy_signal == SIGNAL_BUY_CANDIDATE
        and sentiment_score >= 52
        and sentiment_label == "BULLISH"
    ) or (
        composite >= 72
        and strategy_signal == SIGNAL_BUY_CANDIDATE
        and sentiment_score >= 58
        and sentiment_label == "BULLISH"
        and analyst_norm in ("STRONG BUY", "BUY")
    )

    if strong_buy:
        return ACTION_STRONG_BUY

    if (
        composite >= 65
        and strategy_signal == SIGNAL_BUY_CANDIDATE
        and sentiment_score >= 52
    ):
        return ACTION_INVEST

    if composite >= 55 and strategy_signal in (SIGNAL_BUY_CANDIDATE, SIGNAL_WATCH):
        return ACTION_WATCH

    if composite < 42:
        return ACTION_AVOID

    return ACTION_WATCH


def _sort_key(row: StrategySentimentRow) -> Tuple:
    """
    Sort: Action (STRONG BUY → INVEST → WATCH → AVOID),
    then Analyst (STRONG BUY → BUY → HOLD → SELL → STRONG SELL → N/A),
    then composite score descending.
    """
    action_tier = _ACTION_SORT_ORDER.get(row.suggested_action, 9)
    analyst_norm = _normalize_analyst(row.analyst)
    analyst_tier = _ANALYST_SORT_ORDER.get(analyst_norm, 5)
    return (action_tier, analyst_tier, -row.composite_score, -row.strategy_score, -row.sentiment_score)


def _rank_rows(rows: List[StrategySentimentRow]) -> List[StrategySentimentRow]:
    rows.sort(key=_sort_key)
    for i, r in enumerate(rows, start=1):
        r.rank = i
    return rows


def _build_why(row: StrategySentimentRow) -> str:
    parts = []
    if row.suggested_action == ACTION_STRONG_BUY:
        parts.append("★ Top tier: STRONG BUY alignment (strategy + sentiment + analysts)")
    if row.strategy_signal == SIGNAL_BUY_CANDIDATE:
        parts.append(f"Strategy: BUY setup (score {row.strategy_score:.0f})")
    elif row.strategy_signal == "AVOID":
        parts.append(f"Strategy: avoid (score {row.strategy_score:.0f})")
    else:
        parts.append(f"Strategy: {row.strategy_signal} ({row.strategy_score:.0f})")

    parts.append(f"Sentiment: {row.sentiment_label} ({row.sentiment_score:.0f})")
    if row.analyst != "N/A":
        parts.append(f"Analysts: {row.analyst}")
    if row.sentiment_momentum > 10:
        parts.append("News momentum improving")
    elif row.sentiment_momentum < -10:
        parts.append("News momentum weakening")
    if row.earnings_tone == "POSITIVE":
        parts.append("Positive earnings headlines")
    elif row.earnings_tone == "NEGATIVE":
        parts.append("Negative earnings headlines")
    return " · ".join(parts)


def _resolve_price(ticker: str, fallback: float, indicators: dict) -> Tuple[float, str, str]:
    """Prefer live quote; fall back to analyzer price."""
    from trading.market_data import get_live_quote

    quote = get_live_quote(ticker)
    if quote.get("price") and float(quote["price"]) > 0:
        return (
            float(quote["price"]),
            quote.get("source", "live"),
            quote.get("as_of") or "",
        )
    src = indicators.get("price_source", "daily_close") if indicators else "daily_close"
    return fallback, src, ""


class StrategySentimentScanner:
    """
    Scans full US universe with strategy + sentiment on every stock.
    Ranks all results — STRONG BUY first, then INVEST, by composite score.
    """

    def __init__(self, max_workers: int = 10) -> None:
        self.max_workers = max_workers
        self.analyzer = StockAnalyzer()
        self.sentiment = SentimentAnalyzer(max_news=10)

    def scan(
        self,
        preset: str = "robinhood",
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        enable_ai_notes: bool = True,
        ai_top_n: Optional[int] = None,
    ) -> StrategySentimentSession:
        tickers, min_price, max_price = resolve_scan_universe(preset, result_limit=limit)
        result_cap = limit if limit and limit > 0 else None

        session_id = str(uuid.uuid4())[:8]
        total = len(tickers)
        t0 = time.time()
        rows: List[StrategySentimentRow] = []
        done = [0]

        def _one(ticker: str) -> StrategySentimentRow:
            try:
                tech = self.analyzer.analyze(ticker)
                if tech.error or tech.current_price <= 0:
                    return StrategySentimentRow(
                        ticker=ticker.upper(),
                        error=tech.error or "No price",
                    )

                price, price_source, price_as_of = _resolve_price(
                    ticker.upper(),
                    tech.current_price,
                    tech.indicators or {},
                )

                sent = self.sentiment.analyze(ticker, current_price=price)
                sent_score = sent.overall_sentiment_score if sent.is_valid else 50.0
                news_score = sent.news_sentiment_score if sent.is_valid else 50.0
                analyst = _normalize_analyst(
                    sent.analyst_recommendation if sent.is_valid else "N/A"
                )

                composite = compute_composite_score(
                    tech.overall_score,
                    sent_score,
                    news_score,
                    technical_weight=0.55,
                    sentiment_weight=0.30,
                    news_weight=0.15,
                )

                action = _suggested_action(
                    composite,
                    tech.signal,
                    sent.overall_sentiment_label if sent.is_valid else "NEUTRAL",
                    sent_score,
                    analyst=analyst,
                )

                # Recalc stops from live price
                sl_pct = self.analyzer.stop_loss_pct
                tp_pct = self.analyzer.take_profit_pct
                stop_loss = round(price * (1 - sl_pct / 100), 2)
                take_profit = round(price * (1 + tp_pct / 100), 2)

                row = StrategySentimentRow(
                    ticker=ticker.upper(),
                    price=price,
                    price_source=price_source,
                    price_as_of=price_as_of or "",
                    strategy_signal=tech.signal,
                    strategy_score=tech.overall_score,
                    sentiment_score=sent_score,
                    news_score=news_score,
                    sentiment_label=sent.overall_sentiment_label if sent.is_valid else "NEUTRAL",
                    composite_score=composite,
                    suggested_action=action,
                    analyst=analyst,
                    sector=sent.sector if sent.is_valid else "unknown",
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    sentiment_momentum=sent.sentiment_momentum if sent.is_valid else 0.0,
                    earnings_tone=sent.earnings_tone if sent.is_valid else "NEUTRAL",
                )
                row.why = _build_why(row)
                return row
            except Exception as exc:
                return StrategySentimentRow(ticker=ticker.upper(), error=str(exc)[:120])

        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, total))) as pool:
            futures = {pool.submit(_one, t): t for t in tickers}
            for future in as_completed(futures):
                done[0] += 1
                if progress_callback:
                    try:
                        progress_callback(done[0], total)
                    except Exception:
                        pass
                if result_cap and len(rows) >= result_cap:
                    continue
                try:
                    row = future.result(timeout=90)
                    if not row.is_valid:
                        continue
                    if not price_in_range(row.price, min_price, max_price):
                        continue
                    rows.append(row)
                except Exception as exc:
                    ticker = futures[future]
                    logger.debug("Scan failed %s: %s", ticker, exc)

        if result_cap and len(rows) > result_cap:
            rows = rows[:result_cap]

        _rank_rows(rows)

        ai_provider = "rule-based"
        if enable_ai_notes:
            try:
                from ai.scan_enrichment import enrich_scan_rows
                top = ai_top_n
                if top is None:
                    try:
                        from config.settings import get_settings
                        top = get_settings().AI_SCAN_TOP_N
                    except Exception:
                        top = 20
                n_ai, ai_provider = enrich_scan_rows(rows, top_n=top, enable=True)
                if n_ai:
                    logger.info("Scan AI: %d notes via %s", n_ai, ai_provider)
            except Exception as exc:
                logger.warning("Scan AI enrichment failed: %s", exc)
                ai_provider = "rule-based"

        return StrategySentimentSession(
            session_id=session_id,
            preset=preset,
            universe_size=total,
            scanned=len(rows),
            results=rows,
            elapsed_seconds=round(time.time() - t0, 2),
            ai_scan_provider=ai_provider,
        )

    def refresh_prices(self, rows: List[StrategySentimentRow], max_rows: int = 100) -> int:
        """Refresh live prices for top rows (call after scan for display accuracy)."""
        updated = 0
        for row in rows[:max_rows]:
            try:
                price, src, as_of = _resolve_price(row.ticker, row.price, {})
                if price > 0 and abs(price - row.price) > 0.001:
                    row.price = price
                    row.price_source = src
                    row.price_as_of = as_of
                    sl_pct = self.analyzer.stop_loss_pct
                    tp_pct = self.analyzer.take_profit_pct
                    row.stop_loss = round(price * (1 - sl_pct / 100), 2)
                    row.take_profit = round(price * (1 + tp_pct / 100), 2)
                    updated += 1
            except Exception:
                pass
        return updated

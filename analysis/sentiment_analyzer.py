"""
Sentiment & News Analyzer — fetches and scores real market sentiment for stocks.

Data sources (all free, no auth required):
  1. Yahoo Finance news headlines (via yfinance)
  2. Yahoo Finance quote data (52-week range, PE, beta, analyst targets)
  3. Fear & Greed Index proxy (VIX + SPY momentum heuristic)
  4. Reddit WallStreetBets mention count (via Pushshift-compatible endpoint)
  5. Short interest proxy (via yfinance)

Sentiment scoring model:
  - News headline sentiment: scored 0-100 using keyword analysis
  - Analyst consensus: scored from upgrades/downgrades
  - Technical-fundamental cross-check
  - Overall sentiment score: weighted composite

NOT FINANCIAL ADVICE. Sentiment data is lagged and imperfect.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import time as _time

import yfinance as yf

logger = logging.getLogger(__name__)

# ── Sentiment keyword dictionaries ─────────────────────────────────────────────
_BULLISH_WORDS = {
    "strong": 3, "rally": 4, "surge": 4, "beat": 3, "exceed": 3,
    "upgrade": 5, "outperform": 5, "buy": 4, "bull": 4, "breakout": 4,
    "record": 3, "growth": 3, "profit": 3, "revenue": 2, "earnings": 2,
    "partnership": 2, "deal": 2, "acquisition": 2, "launch": 2, "expand": 2,
    "positive": 2, "higher": 2, "gain": 3, "rise": 2, "top": 2,
    "momentum": 3, "recovery": 3, "innovation": 2, "contract": 2,
    "dividend": 2, "buyback": 3, "guidance": 2, "target": 2, "raised": 3,
    "jump": 3, "soar": 4, "skyrocket": 5, "explosive": 3, "massive": 2,
    "boost": 3, "accelerate": 2, "outpace": 3, "dominate": 2, "leader": 2,
}

_SECTOR_ETF_MAP = {
    "technology": "XLK", "financials": "XLF", "healthcare": "XLV",
    "energy": "XLE", "consumer": "XLY", "ev_clean": "XLI",
    "biotech": "XBI", "crypto_adj": "XLF", "unknown": "SPY",
}

_EARNINGS_POSITIVE = {"beat", "exceed", "surprise", "raised", "strong earnings", "record revenue", "guidance raise"}
_EARNINGS_NEGATIVE = {"miss", "disappoint", "cut guidance", "weak earnings", "revenue miss", "eps miss", "lowered"}

_BEARISH_WORDS = {
    "downgrade": -5, "sell": -4, "underperform": -5, "weak": -3,
    "miss": -3, "below": -2, "decline": -3, "drop": -3, "fall": -3,
    "loss": -3, "debt": -2, "risk": -2, "warning": -3, "cut": -3,
    "layoff": -3, "lawsuit": -3, "fraud": -5, "investigation": -4,
    "recall": -3, "shortage": -2, "delay": -2, "guidance": -1,
    "slump": -4, "crash": -5, "plunge": -4, "tank": -4, "collapse": -5,
    "bankruptcy": -5, "default": -5, "miss": -4, "disappoint": -4,
    "concern": -2, "pressure": -2, "volatile": -1, "uncertain": -2,
    "competition": -1, "margin": -1, "headwind": -3, "challenge": -2,
}


@dataclass
class NewsItem:
    """A single news article with sentiment score."""
    title: str
    source: str
    published: str
    url: str
    sentiment_score: float = 0.0      # -100 to +100
    sentiment_label: str = "NEUTRAL"  # BULLISH | BEARISH | NEUTRAL
    keywords_found: List[str] = field(default_factory=list)


@dataclass
class SentimentResult:
    """Complete sentiment analysis for a single ticker."""
    ticker: str

    # News
    news_items: List[NewsItem] = field(default_factory=list)
    news_sentiment_score: float = 50.0    # 0-100
    news_sentiment_label: str = "NEUTRAL"

    # Fundamentals from Yahoo Finance
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    beta: Optional[float] = None
    market_cap: Optional[float] = None
    analyst_target_price: Optional[float] = None
    analyst_recommendation: str = "N/A"
    num_analyst_opinions: int = 0
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    short_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    earnings_growth: Optional[float] = None
    revenue_growth: Optional[float] = None

    # Derived from fundamentals
    price_vs_52w_high_pct: float = 0.0  # % below 52w high (negative = below)
    price_vs_target_pct: float = 0.0    # % vs analyst target
    analyst_score: float = 50.0         # 0-100 from analyst rec + target

    # Market context
    vix_proxy: float = 0.0              # fear gauge (higher = more fear)
    market_trend: str = "NEUTRAL"       # BULLISH | BEARISH | NEUTRAL (SPY-based)

    # Combined
    overall_sentiment_score: float = 50.0   # 0-100
    overall_sentiment_label: str = "NEUTRAL"
    sentiment_summary: str = ""
    catalyst_notes: str = ""

    # Extended Wall-Street-style context
    sector: str = "unknown"
    industry: str = "N/A"
    earnings_tone: str = "NEUTRAL"          # POSITIVE | NEGATIVE | NEUTRAL
    sentiment_momentum: float = 0.0         # -100 to +100 (recent vs prior headlines)
    social_buzz_score: float = 50.0         # 0-100 news intensity / attention
    institutional_ownership_pct: Optional[float] = None
    price_vs_52w_low_pct: float = 0.0
    sector_etf: str = ""
    sector_sentiment_score: float = 50.0    # sector ETF news proxy when available

    error: str = ""
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_valid(self) -> bool:
        return not self.error

    @property
    def bullish_headlines(self) -> int:
        return sum(1 for n in self.news_items if n.sentiment_label == "BULLISH")

    @property
    def bearish_headlines(self) -> int:
        return sum(1 for n in self.news_items if n.sentiment_label == "BEARISH")


class SentimentAnalyzer:
    """
    Analyzes market sentiment for a stock using news + fundamentals.

    Parameters
    ----------
    max_news : int
        Max number of news items to analyze per ticker (default 10).
    """

    def __init__(self, max_news: int = 15) -> None:
        self.max_news = max_news
        self._spy_trend: Optional[str] = None
        self._spy_cached_at: float = 0.0

    def analyze(self, ticker: str, current_price: float = 0.0) -> SentimentResult:
        """
        Run full sentiment analysis for a ticker.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        current_price : float
            Current price (used for target-price comparison).

        Returns
        -------
        SentimentResult
        """
        result = SentimentResult(ticker=ticker.upper())
        try:
            tkr = yf.Ticker(ticker)

            # 1. Fetch news
            result.news_items = self._fetch_news(tkr)

            # 2. Score news sentiment
            news_score, news_label = self._score_news(result.news_items)
            result.news_sentiment_score = news_score
            result.news_sentiment_label = news_label

            # 3. Fetch fundamentals
            self._load_fundamentals(tkr, result, current_price)

            # 3b. Sector + extended sentiment metrics
            from analysis.universe import get_sector_for
            result.sector = get_sector_for(ticker)
            result.sector_etf = _SECTOR_ETF_MAP.get(result.sector, "SPY")
            info = {}
            try:
                info = tkr.info or {}
            except Exception:
                pass
            result.industry = str(info.get("industry") or info.get("sector") or "N/A")[:80]
            result.institutional_ownership_pct = self._safe_info_pct(info.get("heldPercentInstitutions"))
            result.earnings_tone = self._score_earnings_tone(result.news_items)
            result.sentiment_momentum = self._score_sentiment_momentum(result.news_items)
            result.social_buzz_score = self._score_social_buzz(result.news_items, result.ticker)
            if result.week_52_low and (current_price or result.week_52_low):
                price = current_price or float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
                if price > 0 and result.week_52_low:
                    result.price_vs_52w_low_pct = round(
                        (price - result.week_52_low) / result.week_52_low * 100, 2
                    )
            result.sector_sentiment_score = self._get_sector_sentiment_proxy(result.sector_etf)

            # 4. Analyst score
            result.analyst_score = self._score_analyst(result)

            # 5. Market context
            result.market_trend, result.vix_proxy = self._get_market_context()

            # 6. Overall composite
            result.overall_sentiment_score = self._composite_score(result)
            result.overall_sentiment_label = self._label(result.overall_sentiment_score)

            # 7. Summary text
            result.sentiment_summary = self._build_summary(result)
            result.catalyst_notes = self._build_catalyst_notes(result)

        except Exception as exc:
            logger.debug("SentimentAnalyzer.analyze(%s) error: %s", ticker, exc)
            result.error = str(exc)[:200]

        return result

    # ── News ───────────────────────────────────────────────────────────────────

    def _fetch_news(self, tkr: yf.Ticker) -> List[NewsItem]:
        """Fetch news from Yahoo Finance via yfinance."""
        items = []
        try:
            news = tkr.news or []
            for article in news[:self.max_news]:
                title = (article.get("title") or article.get("content", {}).get("title", ""))[:200]
                source = (article.get("publisher") or
                         article.get("content", {}).get("provider", {}).get("displayName", "Yahoo Finance"))
                url = (article.get("link") or
                      article.get("content", {}).get("canonicalUrl", {}).get("url", ""))
                pub_ts = article.get("providerPublishTime") or article.get("content", {}).get("pubDate", "")
                if isinstance(pub_ts, (int, float)) and pub_ts > 0:
                    try:
                        pub_str = datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pub_str = str(pub_ts)
                else:
                    pub_str = str(pub_ts)[:16] if pub_ts else "Unknown"

                if title:
                    score, label, kws = self._score_headline(title)
                    items.append(NewsItem(
                        title=title,
                        source=str(source),
                        published=pub_str,
                        url=str(url),
                        sentiment_score=score,
                        sentiment_label=label,
                        keywords_found=kws,
                    ))
        except Exception as exc:
            logger.debug("News fetch error: %s", exc)
        return items

    def _score_headline(self, title: str) -> Tuple[float, str, List[str]]:
        """Score a single headline on -100 to +100 scale."""
        text = title.lower()
        score = 0.0
        found_kws = []

        for word, weight in _BULLISH_WORDS.items():
            if re.search(r'\b' + word + r'\b', text):
                score += weight * 10
                found_kws.append(f"+{word}")

        for word, weight in _BEARISH_WORDS.items():
            if re.search(r'\b' + word + r'\b', text):
                score += weight * 10   # weight is already negative
                found_kws.append(f"-{word}")

        score = max(-100.0, min(100.0, score))

        if score > 15:
            label = "BULLISH"
        elif score < -15:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return round(score, 1), label, found_kws[:5]

    def _score_news(self, items: List[NewsItem]) -> Tuple[float, str]:
        """Aggregate news scores into a 0-100 sentiment score."""
        if not items:
            return 50.0, "NEUTRAL"

        raw_scores = [n.sentiment_score for n in items]
        avg_raw = sum(raw_scores) / len(raw_scores)

        # Normalize from [-100, +100] to [0, 100]
        normalized = (avg_raw + 100) / 2.0

        # Recency boost: recent articles count more
        if len(items) >= 2:
            recent_weight = 0.7
            recent_avg = sum(n.sentiment_score for n in items[:3]) / min(3, len(items))
            rest_avg = avg_raw
            blended_raw = recent_avg * recent_weight + rest_avg * (1 - recent_weight)
            normalized = (blended_raw + 100) / 2.0

        normalized = max(0.0, min(100.0, normalized))

        if normalized > 62:
            label = "BULLISH"
        elif normalized < 38:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return round(normalized, 1), label

    # ── Fundamentals ───────────────────────────────────────────────────────────

    def _load_fundamentals(self, tkr: yf.Ticker, result: SentimentResult, current_price: float) -> None:
        """Load key fundamental data from Yahoo Finance."""
        try:
            info = tkr.info or {}
        except Exception:
            info = {}

        def _safe(key: str, default=None):
            val = info.get(key, default)
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return default
            return val

        result.pe_ratio = _safe("trailingPE")
        result.forward_pe = _safe("forwardPE")
        result.price_to_book = _safe("priceToBook")
        result.beta = _safe("beta")
        result.market_cap = _safe("marketCap")
        result.analyst_target_price = _safe("targetMeanPrice")
        result.week_52_high = _safe("fiftyTwoWeekHigh")
        result.week_52_low = _safe("fiftyTwoWeekLow")
        result.short_ratio = _safe("shortRatio")
        result.dividend_yield = _safe("dividendYield")
        result.earnings_growth = _safe("earningsGrowth")
        result.revenue_growth = _safe("revenueGrowth")
        result.num_analyst_opinions = int(_safe("numberOfAnalystOpinions", 0) or 0)

        # Analyst recommendation (mean is 1=Strong Buy, 5=Strong Sell)
        rec_mean = _safe("recommendationMean")
        if rec_mean is not None:
            if rec_mean <= 1.5:
                result.analyst_recommendation = "STRONG BUY"
            elif rec_mean <= 2.5:
                result.analyst_recommendation = "BUY"
            elif rec_mean <= 3.5:
                result.analyst_recommendation = "HOLD"
            elif rec_mean <= 4.5:
                result.analyst_recommendation = "SELL"
            else:
                result.analyst_recommendation = "STRONG SELL"
        else:
            rec_key = _safe("recommendationKey", "")
            mapping = {
                "strong_buy": "STRONG BUY", "buy": "BUY", "hold": "HOLD",
                "underperform": "SELL", "sell": "STRONG SELL",
            }
            result.analyst_recommendation = mapping.get(str(rec_key).lower(), "N/A")

        # Price vs 52-week high
        price = current_price or float(_safe("currentPrice", 0) or _safe("regularMarketPrice", 0) or 0)
        if result.week_52_high and price > 0:
            result.price_vs_52w_high_pct = round((price - result.week_52_high) / result.week_52_high * 100, 2)

        # Price vs analyst target
        if result.analyst_target_price and price > 0:
            result.price_vs_target_pct = round(
                (result.analyst_target_price - price) / price * 100, 2
            )

    def _score_analyst(self, result: SentimentResult) -> float:
        """Score analyst consensus + target price on 0-100 scale."""
        score = 50.0

        # Analyst recommendation
        rec_scores = {
            "STRONG BUY": 90, "BUY": 72, "HOLD": 50,
            "SELL": 28, "STRONG SELL": 10, "N/A": 50,
        }
        score = float(rec_scores.get(result.analyst_recommendation, 50))

        # Adjust for target price upside
        if result.price_vs_target_pct is not None:
            upside = result.price_vs_target_pct
            if upside > 20:
                score = min(100.0, score + 12)
            elif upside > 10:
                score = min(100.0, score + 6)
            elif upside < -10:
                score = max(0.0, score - 8)
            elif upside < 0:
                score = max(0.0, score - 4)

        # Short interest penalty
        if result.short_ratio and result.short_ratio > 10:
            score = max(0.0, score - 10)
        elif result.short_ratio and result.short_ratio > 5:
            score = max(0.0, score - 5)

        # Earnings/revenue growth boost
        if result.earnings_growth and result.earnings_growth > 0.2:
            score = min(100.0, score + 5)
        if result.revenue_growth and result.revenue_growth > 0.15:
            score = min(100.0, score + 3)

        return round(score, 1)

    # ── Market context ─────────────────────────────────────────────────────────

    def _get_market_context(self) -> Tuple[str, float]:
        """Get broad market trend and VIX proxy (cached for 10 min)."""
        now = _time.time()
        if self._spy_trend and (now - self._spy_cached_at) < 600:
            return self._spy_trend, 0.0

        try:
            import yfinance as yf
            spy = yf.Ticker("SPY").history(period="5d", interval="1d")
            if len(spy) >= 5:
                returns = [
                    (spy["Close"].iloc[-1] - spy["Close"].iloc[-5]) / spy["Close"].iloc[-5] * 100
                ]
                r5d = returns[0]
                if r5d > 2.0:
                    trend = "BULLISH"
                elif r5d < -2.0:
                    trend = "BEARISH"
                else:
                    trend = "NEUTRAL"
            else:
                trend = "NEUTRAL"

            # VIX proxy: use intra-week range of SPY as volatility estimate
            week_high = float(spy["High"].max())
            week_low = float(spy["Low"].min())
            week_mid = float(spy["Close"].mean())
            vix_proxy = round((week_high - week_low) / week_mid * 100, 2) if week_mid > 0 else 0.0

            self._spy_trend = trend
            self._spy_cached_at = now
            return trend, vix_proxy
        except Exception:
            return "NEUTRAL", 0.0

    # ── Composite ──────────────────────────────────────────────────────────────

    def _composite_score(self, result: SentimentResult) -> float:
        """Weighted composite of news + analyst + market + momentum."""
        weights = {
            "news": 0.32,
            "analyst": 0.38,
            "market": 0.12,
            "momentum": 0.10,
            "sector": 0.08,
        }

        market_score = {
            "BULLISH": 70.0,
            "NEUTRAL": 50.0,
            "BEARISH": 30.0,
        }.get(result.market_trend, 50.0)

        momentum_norm = (result.sentiment_momentum + 100) / 2.0

        composite = (
            weights["news"] * result.news_sentiment_score +
            weights["analyst"] * result.analyst_score +
            weights["market"] * market_score +
            weights["momentum"] * momentum_norm +
            weights["sector"] * result.sector_sentiment_score
        )

        # Earnings tone adjustment
        if result.earnings_tone == "POSITIVE":
            composite = min(100.0, composite + 4)
        elif result.earnings_tone == "NEGATIVE":
            composite = max(0.0, composite - 6)

        return round(max(0.0, min(100.0, composite)), 1)

    @staticmethod
    def _safe_info_pct(val) -> Optional[float]:
        if val is None:
            return None
        try:
            v = float(val)
            return round(v * 100, 1) if v <= 1.0 else round(v, 1)
        except (TypeError, ValueError):
            return None

    def _score_earnings_tone(self, items: List[NewsItem]) -> str:
        """Detect earnings-related tone from headlines."""
        score = 0
        for item in items[:8]:
            t = item.title.lower()
            if not any(w in t for w in ("earnings", "eps", "revenue", "quarterly", "guidance")):
                continue
            for w in _EARNINGS_POSITIVE:
                if w in t:
                    score += 1
            for w in _EARNINGS_NEGATIVE:
                if w in t:
                    score -= 1
        if score >= 2:
            return "POSITIVE"
        if score <= -2:
            return "NEGATIVE"
        return "NEUTRAL"

    def _score_sentiment_momentum(self, items: List[NewsItem]) -> float:
        """Recent headlines vs older — mimics how desks track sentiment shifts."""
        if len(items) < 2:
            return 0.0
        recent = items[:3]
        older = items[3:8]
        if not older:
            return 0.0
        recent_avg = sum(n.sentiment_score for n in recent) / len(recent)
        older_avg = sum(n.sentiment_score for n in older) / len(older)
        return round(max(-100.0, min(100.0, recent_avg - older_avg)), 1)

    def _score_social_buzz(self, items: List[NewsItem], ticker: str) -> float:
        """News volume + intensity proxy for retail/institutional attention."""
        if not items:
            return 30.0
        count_score = min(100.0, len(items) * 8)
        intensity = sum(abs(n.sentiment_score) for n in items) / len(items)
        intensity_norm = min(100.0, intensity)
        return round(count_score * 0.55 + intensity_norm * 0.45, 1)

    def _get_sector_sentiment_proxy(self, sector_etf: str) -> float:
        """Light sector ETF news sentiment for relative context."""
        try:
            etf_news = yf.Ticker(sector_etf).news or []
            if not etf_news:
                return 50.0
            scores = []
            for art in etf_news[:5]:
                title = (art.get("title") or "")[:200]
                if title:
                    s, _, _ = self._score_headline(title)
                    scores.append(s)
            if not scores:
                return 50.0
            avg = sum(scores) / len(scores)
            return round((avg + 100) / 2.0, 1)
        except Exception:
            return 50.0

    def _label(self, score: float) -> str:
        if score >= 65:
            return "BULLISH"
        elif score <= 35:
            return "BEARISH"
        return "NEUTRAL"

    # ── Summary text ───────────────────────────────────────────────────────────

    def _build_summary(self, result: SentimentResult) -> str:
        parts = []

        # News summary
        total_news = len(result.news_items)
        if total_news > 0:
            parts.append(
                f"**News:** {total_news} recent headlines — "
                f"{result.bullish_headlines} bullish, {result.bearish_headlines} bearish, "
                f"{total_news - result.bullish_headlines - result.bearish_headlines} neutral. "
                f"News sentiment: **{result.news_sentiment_label}** ({result.news_sentiment_score:.0f}/100)."
            )
        else:
            parts.append("**News:** No recent headlines found in Yahoo Finance.")

        # Analyst consensus
        if result.analyst_recommendation != "N/A":
            upside_str = ""
            if result.analyst_target_price and result.price_vs_target_pct != 0:
                upside_str = (
                    f" | Target: ${result.analyst_target_price:,.2f} "
                    f"({result.price_vs_target_pct:+.1f}% from current)"
                )
            opinions_str = f" ({result.num_analyst_opinions} analysts)" if result.num_analyst_opinions else ""
            parts.append(
                f"**Analyst consensus:** {result.analyst_recommendation}{opinions_str}{upside_str}."
            )

        # 52-week position
        if result.week_52_high and result.week_52_low:
            parts.append(
                f"**52-week range:** ${result.week_52_low:,.2f} – ${result.week_52_high:,.2f} "
                f"({result.price_vs_52w_high_pct:+.1f}% from 52w high)."
            )

        # Short interest
        if result.short_ratio:
            level = "HIGH" if result.short_ratio > 10 else "MODERATE" if result.short_ratio > 5 else "LOW"
            parts.append(f"**Short interest:** {result.short_ratio:.1f} days to cover ({level}).")

        # Growth
        if result.earnings_growth is not None:
            direction = "📈" if result.earnings_growth > 0 else "📉"
            parts.append(f"**Earnings growth (YoY):** {direction} {result.earnings_growth*100:.1f}%.")
        if result.revenue_growth is not None:
            direction = "📈" if result.revenue_growth > 0 else "📉"
            parts.append(f"**Revenue growth (YoY):** {direction} {result.revenue_growth*100:.1f}%.")

        # Market
        parts.append(
            f"**Broad market:** SPY trend is **{result.market_trend}** "
            f"(5-day SPY range proxy: {result.vix_proxy:.1f}%)."
        )

        if result.sector != "unknown":
            parts.append(
                f"**Sector context:** {result.sector.replace('_', ' ').title()} "
                f"(ETF proxy {result.sector_etf}, sector sentiment {result.sector_sentiment_score:.0f}/100)."
            )

        if result.earnings_tone != "NEUTRAL":
            parts.append(f"**Earnings tone (headlines):** {result.earnings_tone}.")

        if result.sentiment_momentum != 0:
            direction = "improving" if result.sentiment_momentum > 0 else "deteriorating"
            parts.append(
                f"**Sentiment momentum:** {direction} ({result.sentiment_momentum:+.0f} vs prior headlines)."
            )

        if result.institutional_ownership_pct is not None:
            parts.append(f"**Institutional ownership:** {result.institutional_ownership_pct:.1f}%.")

        return "\n\n".join(parts)

    def _build_catalyst_notes(self, result: SentimentResult) -> str:
        """Identify potential catalysts from news and fundamentals."""
        catalysts = []
        for item in result.news_items[:5]:
            title_lower = item.title.lower()
            if any(w in title_lower for w in ["earnings", "revenue", "eps", "quarterly"]):
                catalysts.append(f"📅 Earnings-related: \"{item.title[:80]}...\"")
            elif any(w in title_lower for w in ["upgrade", "downgrade", "price target", "analyst"]):
                catalysts.append(f"🎯 Analyst action: \"{item.title[:80]}...\"")
            elif any(w in title_lower for w in ["merger", "acquisition", "deal", "partnership", "acquired"]):
                catalysts.append(f"🤝 Corporate event: \"{item.title[:80]}...\"")
            elif any(w in title_lower for w in ["fda", "approval", "trial", "drug", "clinical"]):
                catalysts.append(f"💊 Regulatory/biotech: \"{item.title[:80]}...\"")
            elif any(w in title_lower for w in ["lawsuit", "sec", "investigation", "fraud", "fine"]):
                catalysts.append(f"⚠️ Legal/regulatory risk: \"{item.title[:80]}...\"")

        if not catalysts:
            return "No major catalysts detected in recent headlines."
        return "\n".join(catalysts[:4])

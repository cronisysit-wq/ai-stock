"""
Senior Wall Street Advisor — institutional-grade deep stock research.

Produces sell-side-style educational research notes combining:
  - Technical analysis
  - News & headline sentiment
  - Analyst consensus & price targets
  - Sector / macro context
  - Bull case / bear case / risk factors
  - Catalyst calendar

Modeled after how Sr. advisors at major brokerages structure morning notes —
but strictly NON-ACTIONABLE (no buy/sell orders).

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from analysis.integrated_analysis import IntegratedAnalysis
    from analysis.sentiment_analyzer import SentimentResult

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n---\n"
    "⚠️ **NOT FINANCIAL ADVICE.** This is an AI-generated educational research simulation. "
    "It does not represent Goldman Sachs, Morgan Stanley, JPMorgan, or any registered broker-dealer. "
    "Ratings are illustrative only — not investment recommendations. "
    "Consult a licensed financial advisor before investing."
)


class ResearchRating(str, Enum):
    """Educational attractiveness rating — NOT a trade recommendation."""
    HIGHLY_ATTRACTIVE = "Highly Attractive"
    ATTRACTIVE = "Attractive"
    NEUTRAL = "Neutral"
    UNATTRACTIVE = "Unattractive"
    HIGH_RISK = "High Risk / Unfavorable"


@dataclass
class WallStreetResearchNote:
    """Full Sr. advisor research note."""
    ticker: str
    rating: ResearchRating
    conviction_score: float          # 0-100 educational confidence in data alignment
    executive_summary: str
    investment_thesis: str
    bull_case: str
    bear_case: str
    technical_view: str
    sentiment_analysis: str
    fundamental_context: str
    sector_macro: str
    risk_factors: str
    catalyst_calendar: str
    analyst_consensus_view: str
    verdict: str
    price: float = 0.0
    composite_score: float = 0.0
    is_actionable: bool = False
    ai_powered: bool = False
    disclaimer: str = field(default_factory=lambda: _DISCLAIMER)

    @property
    def full_report(self) -> str:
        badge = "🤖 AI-Powered Sr. Advisor" if self.ai_powered else "📊 Rule-Based Sr. Advisor"
        header = (
            f"# 🏛️ Senior Wall Street Research — {self.ticker}\n"
            f"**{badge}** | Rating: **{self.rating.value}** | "
            f"Conviction: **{self.conviction_score:.0f}/100**\n\n"
        )
        sections = [
            ("Executive Summary", self.executive_summary),
            ("Investment Thesis", self.investment_thesis),
            ("Bull Case", self.bull_case),
            ("Bear Case", self.bear_case),
            ("Technical View", self.technical_view),
            ("Sentiment & News Analysis", self.sentiment_analysis),
            ("Fundamental Context", self.fundamental_context),
            ("Sector & Macro", self.sector_macro),
            ("Analyst Consensus", self.analyst_consensus_view),
            ("Catalyst Calendar", self.catalyst_calendar),
            ("Key Risk Factors", self.risk_factors),
            ("Verdict", self.verdict),
        ]
        body = "\n\n".join(f"### {title}\n{text}" for title, text in sections if text)
        return f"{header}{body}{self.disclaimer}"


def _derive_rating(composite: float, sentiment_label: str, technical: float) -> ResearchRating:
    if composite >= 72 and technical >= 65 and sentiment_label == "BULLISH":
        return ResearchRating.HIGHLY_ATTRACTIVE
    if composite >= 62 and technical >= 55:
        return ResearchRating.ATTRACTIVE
    if composite <= 38 or (sentiment_label == "BEARISH" and technical < 45):
        return ResearchRating.HIGH_RISK
    if composite <= 45:
        return ResearchRating.UNATTRACTIVE
    return ResearchRating.NEUTRAL


def _conviction_score(composite: float, technical: float, sentiment: float, momentum: float = 0) -> float:
    """How aligned are technicals, sentiment, and momentum."""
    spread = max(abs(technical - sentiment), abs(technical - composite))
    base = composite - spread * 0.3
    if momentum > 15:
        base = min(100, base + 5)
    elif momentum < -15:
        base = max(0, base - 5)
    return round(max(0, min(100, base)), 1)


def generate_research_note(
    analysis: "IntegratedAnalysis",
    account_equity: float = 25_000.0,
    daily_target_pct: float = 0.75,
) -> WallStreetResearchNote:
    """
    Generate a Sr. Wall Street-style deep research note from integrated analysis.
    """
    from ai.analyst import call_ai_stock

    sent = analysis.sentiment
    momentum = sent.sentiment_momentum if sent else 0.0
    rating = _derive_rating(
        analysis.composite_score, analysis.sentiment_label, analysis.technical_score
    )
    conviction = _conviction_score(
        analysis.composite_score, analysis.technical_score,
        analysis.sentiment_score, momentum,
    )

    headlines = "\n".join(
        f"  • [{n.sentiment_label}] {n.title[:110]}"
        for n in analysis.news_headlines[:8]
    ) or "  No recent headlines."

    fund_block = _format_fundamentals(sent) if sent else "Fundamental data unavailable."

    target_usd = account_equity * daily_target_pct / 100
    prompt = f"""You are a Senior Wall Street Research Analyst writing an EDUCATIONAL morning research note.
This is NOT financial advice. Never say buy, sell, or place an order.

Structure your response EXACTLY with these markdown section headers:

## Executive Summary
(2-3 sentences — key takeaway for a portfolio manager)

## Investment Thesis
(Why this name matters now — business + market context)

## Bull Case
(3 bullet points — upside drivers from data)

## Bear Case
(3 bullet points — what could go wrong)

## Technical View
(Trend, momentum, volume, ATR context — score {analysis.technical_score:.0f}/100)

## Sentiment & News Analysis
(Headline sentiment {analysis.sentiment_score:.0f}/100, label {analysis.sentiment_label}, news {analysis.news_score:.0f}/100)
Recent headlines:
{headlines}
Catalysts: {analysis.catalyst_notes or 'None'}

## Fundamental Context
{fund_block}

## Sector & Macro
(Sector: {analysis.sector}, market trend, sector sentiment context)

## Analyst Consensus
({analysis.analyst_consensus} — integrate target upside if available)

## Catalyst Calendar
(Upcoming events from news — earnings, FDA, analyst days, etc.)

## Key Risk Factors
(Top 3-4 risks — macro, sector, company-specific)

## Verdict
(Educational rating context: {rating.value}. Reference {daily_target_pct}% daily goal ≈ ${target_usd:,.0f} on ${account_equity:,.0f} — explain volatility/capital needed. NOT a trade call.)

DATA:
Ticker: {analysis.ticker} | Price: ${analysis.price:,.2f}
Composite: {analysis.composite_score:.0f}/100 | Signal: {analysis.signal}
Volume ratio: {analysis.volume_ratio:.1f}x | ATR%: {analysis.atr_pct:.2f}%
Earnings tone: {getattr(sent, 'earnings_tone', 'N/A') if sent else 'N/A'}
Sentiment momentum: {momentum:+.0f}
Technical context: {analysis.explanation[:350]}

RULES: Professional tone like Goldman/Morgan Stanley research. Never actionable orders."""

    text, provider = call_ai_stock(prompt, system="You are a Senior Wall Street Research Analyst. Educational only.")
    ai_powered = text is not None

    if text:
        sections = _parse_sections(text)
        return WallStreetResearchNote(
            ticker=analysis.ticker,
            rating=rating,
            conviction_score=conviction,
            executive_summary=sections.get("Executive Summary", text[:400]),
            investment_thesis=sections.get("Investment Thesis", ""),
            bull_case=sections.get("Bull Case", ""),
            bear_case=sections.get("Bear Case", ""),
            technical_view=sections.get("Technical View", ""),
            sentiment_analysis=sections.get("Sentiment & News Analysis", ""),
            fundamental_context=sections.get("Fundamental Context", fund_block),
            sector_macro=sections.get("Sector & Macro", ""),
            risk_factors=sections.get("Key Risk Factors", ""),
            catalyst_calendar=sections.get("Catalyst Calendar", analysis.catalyst_notes),
            analyst_consensus_view=sections.get("Analyst Consensus", analysis.analyst_consensus),
            verdict=sections.get("Verdict", ""),
            price=analysis.price,
            composite_score=analysis.composite_score,
            ai_powered=ai_powered,
        )

    return _rule_based_note(analysis, rating, conviction, sent, target_usd, daily_target_pct, account_equity)


def generate_from_sentiment(
    sent: "SentimentResult",
    technical_score: float = 50.0,
    price: float = 0.0,
    signal: str = "WATCH",
    explanation: str = "",
    account_equity: float = 25_000.0,
    daily_target_pct: float = 0.75,
) -> WallStreetResearchNote:
    """Build research note from sentiment-only (no full integrated scan)."""
    from analysis.integrated_analysis import IntegratedAnalysis, compute_composite_score

    composite = compute_composite_score(
        technical_score, sent.overall_sentiment_score, sent.news_sentiment_score,
    )
    integrated = IntegratedAnalysis(
        ticker=sent.ticker,
        price=price or 0.0,
        technical_score=technical_score,
        sentiment_score=sent.overall_sentiment_score,
        news_score=sent.news_sentiment_score,
        composite_score=composite,
        signal=signal,
        explanation=explanation,
        sentiment=sent,
        news_headlines=sent.news_items[:8],
        sentiment_label=sent.overall_sentiment_label,
        analyst_consensus=sent.analyst_recommendation,
        catalyst_notes=sent.catalyst_notes,
        sector=getattr(sent, "sector", "unknown"),
        industry=getattr(sent, "industry", "N/A"),
        earnings_tone=getattr(sent, "earnings_tone", "NEUTRAL"),
        sentiment_momentum=getattr(sent, "sentiment_momentum", 0.0),
    )
    return generate_research_note(integrated, account_equity, daily_target_pct)


def _format_fundamentals(sent: "SentimentResult") -> str:
    parts = []
    if sent.pe_ratio:
        parts.append(f"PE: {sent.pe_ratio:.1f}")
    if sent.forward_pe:
        parts.append(f"Forward PE: {sent.forward_pe:.1f}")
    if sent.beta:
        parts.append(f"Beta: {sent.beta:.2f}")
    if sent.market_cap:
        parts.append(f"Market cap: ${sent.market_cap/1e9:.1f}B")
    if sent.earnings_growth is not None:
        parts.append(f"Earnings growth: {sent.earnings_growth*100:.1f}%")
    if sent.revenue_growth is not None:
        parts.append(f"Revenue growth: {sent.revenue_growth*100:.1f}%")
    if sent.short_ratio:
        parts.append(f"Short ratio: {sent.short_ratio:.1f} days")
    if sent.institutional_ownership_pct:
        parts.append(f"Institutional ownership: {sent.institutional_ownership_pct:.1f}%")
    if sent.week_52_high and sent.week_52_low:
        parts.append(f"52w range: ${sent.week_52_low:,.0f}–${sent.week_52_high:,.0f}")
    return " | ".join(parts) if parts else "Limited fundamental data available."


def _parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def _rule_based_note(
    a: "IntegratedAnalysis",
    rating: ResearchRating,
    conviction: float,
    sent: Optional["SentimentResult"],
    target_usd: float,
    daily_target_pct: float,
    account_equity: float,
) -> WallStreetResearchNote:
    align = "converging" if abs(a.technical_score - a.sentiment_score) < 15 else "diverging"
    momentum_note = ""
    if sent and sent.sentiment_momentum != 0:
        momentum_note = (
            f" Sentiment momentum is {'positive' if sent.sentiment_momentum > 0 else 'negative'} "
            f"({sent.sentiment_momentum:+.0f})."
        )

    return WallStreetResearchNote(
        ticker=a.ticker,
        rating=rating,
        conviction_score=conviction,
        executive_summary=(
            f"{a.ticker} scores **{a.composite_score:.0f}/100** composite "
            f"(technical {a.technical_score:.0f}, sentiment {a.sentiment_score:.0f}). "
            f"Technicals and sentiment are **{align}**. Rating: **{rating.value}**."
        ),
        investment_thesis=(
            f"From a professional desk perspective, {a.ticker} sits in **{a.sector.replace('_', ' ')}** "
            f"with signal context **{a.signal}**. {a.explanation[:250]}"
        ),
        bull_case=(
            f"• Composite score {a.composite_score:.0f}/100 with analyst view **{a.analyst_consensus}**\n"
            f"• News sentiment {a.news_score:.0f}/100 ({a.sentiment_label})\n"
            f"• Technical score {a.technical_score:.0f}/100 supports trend/momentum read"
        ),
        bear_case=(
            "• Sentiment can reverse quickly on macro shocks\n"
            "• Single-stock concentration risk for aggressive daily targets\n"
            f"• {a.catalyst_notes[:150] if a.catalyst_notes else 'Monitor upcoming earnings and macro data'}"
        ),
        technical_view=(
            f"Technical score **{a.technical_score:.0f}/100**. Volume {a.volume_ratio:.1f}x average. "
            f"ATR {a.atr_pct:.2f}%. {a.explanation[:200]}"
        ),
        sentiment_analysis=(
            f"Overall sentiment **{a.sentiment_label}** ({a.sentiment_score:.0f}/100). "
            f"News score {a.news_score:.0f}/100.{momentum_note} "
            f"{a.catalyst_notes[:200] if a.catalyst_notes else ''}"
        ),
        fundamental_context=_format_fundamentals(sent) if sent else "N/A",
        sector_macro=(
            f"Sector: **{getattr(a, 'sector', 'unknown')}**. "
            f"Broad market trend: **{sent.market_trend if sent else 'NEUTRAL'}**."
        ),
        risk_factors=(
            "• Market-wide drawdown risk\n• Headline-driven volatility\n"
            "• Gap risk around earnings\n• Liquidity varies by market cap"
        ),
        catalyst_calendar=a.catalyst_notes or "No major catalysts flagged in recent headlines.",
        analyst_consensus_view=f"Street consensus: **{a.analyst_consensus}**.",
        verdict=(
            f"Educational rating: **{rating.value}** (conviction {conviction:.0f}/100). "
            f"A {daily_target_pct}% daily reference on ${account_equity:,.0f} ≈ ${target_usd:,.0f}/day — "
            f"requires favorable volatility and is NOT guaranteed."
        ),
        price=a.price,
        composite_score=a.composite_score,
        ai_powered=False,
    )

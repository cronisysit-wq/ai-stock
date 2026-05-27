"""
Institutional AI Advisor — persona-based analysis combining
technicals, news sentiment, and fundamentals.

Personas (educational voice, NOT real financial advice):
  - Warren Buffett / Berkshire Hathaway — value, moat, long-term quality
  - Vanguard — low-cost indexing, diversification, patience
  - BlackRock — macro, ETF flows, institutional risk
  - Fidelity — research-driven, retirement-oriented balance
  - Charles Schwab — accessible investor education, balanced risk
  - Robinhood — simplified, momentum-aware (still non-actionable)

Hard rules: never actionable orders, always disclaimer, is_actionable=False.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from analysis.integrated_analysis import IntegratedAnalysis

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n---\n"
    "⚠️ **NOT FINANCIAL ADVICE.** This is an AI-generated educational persona simulation. "
    "It does not represent Warren Buffett, Berkshire Hathaway, Vanguard, BlackRock, "
    "Fidelity, Charles Schwab, Robinhood, or any real institution. "
    "Past performance does not guarantee future results. "
    "Consult a licensed financial advisor before investing."
)


class AdvisorPersona(str, Enum):
    BUFFETT = "warren_buffett"
    BERKSHIRE = "berkshire_hathaway"
    VANGUARD = "vanguard"
    BLACKROCK = "blackrock"
    FIDELITY = "fidelity"
    SCHWAB = "charles_schwab"
    ROBINHOOD = "robinhood"


PERSONA_LABELS = {
    AdvisorPersona.BUFFETT: "🎩 Warren Buffett — Value & Quality",
    AdvisorPersona.BERKSHIRE: "🏛️ Berkshire Hathaway — Long-Term Compounding",
    AdvisorPersona.VANGUARD: "📊 Vanguard — Index & Diversification",
    AdvisorPersona.BLACKROCK: "🌍 BlackRock — Macro & Institutional Risk",
    AdvisorPersona.FIDELITY: "🔬 Fidelity — Research & Balance",
    AdvisorPersona.SCHWAB: "💼 Charles Schwab — Accessible Investor",
    AdvisorPersona.ROBINHOOD: "🟢 Robinhood — Simplified Momentum View",
}

# Persona-specific composite weights (technical, sentiment, news)
PERSONA_WEIGHTS = {
    AdvisorPersona.BUFFETT: (0.35, 0.35, 0.30),
    AdvisorPersona.BERKSHIRE: (0.30, 0.40, 0.30),
    AdvisorPersona.VANGUARD: (0.40, 0.35, 0.25),
    AdvisorPersona.BLACKROCK: (0.45, 0.30, 0.25),
    AdvisorPersona.FIDELITY: (0.42, 0.33, 0.25),
    AdvisorPersona.SCHWAB: (0.45, 0.30, 0.25),
    AdvisorPersona.ROBINHOOD: (0.55, 0.25, 0.20),
}

PERSONA_SYSTEM = {
    AdvisorPersona.BUFFETT: (
        "You speak in the educational style of a value investor inspired by Warren Buffett. "
        "Focus on business quality, margin of safety, understandable businesses, and long holding periods. "
        "Reference news and sentiment only as context for whether the market is mispricing quality. "
        "Never say buy or sell — use 'the business appears attractive/unattractive based on available data'."
    ),
    AdvisorPersona.BERKSHIRE: (
        "You speak as an educational voice inspired by Berkshire Hathaway's philosophy: "
        "permanent capital, wonderful businesses at fair prices, insurance-float mindset, "
        "and ignoring short-term noise. Integrate news as risk factors, not trade triggers."
    ),
    AdvisorPersona.VANGUARD: (
        "You speak as an educational voice inspired by Vanguard: low costs, broad diversification, "
        "time in market over timing, and aligning risk with goals. Emphasize whether a single stock "
        "fits a diversified portfolio context. Never recommend concentrated bets."
    ),
    AdvisorPersona.BLACKROCK: (
        "You speak as an educational institutional analyst inspired by BlackRock: macro trends, "
        "ETF flows, geopolitical risk, factor exposure, and portfolio-level risk. "
        "Connect news catalysts to systemic risk, not individual trade calls."
    ),
    AdvisorPersona.FIDELITY: (
        "You speak as an educational research analyst inspired by Fidelity: balance sheets, "
        "analyst consensus, earnings quality, and suitability for different investor profiles. "
        "Integrate news and sentiment into a research note format."
    ),
    AdvisorPersona.SCHWAB: (
        "You speak as an educational advisor inspired by Charles Schwab: clear plain English, "
        "goal-based planning, risk tolerance, and practical context for retail investors. "
        "Explain how news and technicals fit together without giving orders."
    ),
    AdvisorPersona.ROBINHOOD: (
        "You speak as a simplified educational voice inspired by modern retail platforms: "
        "clear, concise, momentum and volume context, but still non-actionable. "
        "Explain what the data shows without saying 'buy now' or 'sell now'."
    ),
}


@dataclass
class InstitutionalAdvice:
    """Persona-based advisory output."""
    persona: AdvisorPersona
    ticker: str
    narrative: str
    composite_score: float
    technical_score: float
    sentiment_score: float
    news_score: float
    sentiment_label: str
    headline_summary: str
    catalyst_summary: str
    daily_target_context: str = ""
    is_actionable: bool = False
    ai_powered: bool = False
    ai_provider: str = "rule-based"
    disclaimer: str = field(default_factory=lambda: _DISCLAIMER)

    @property
    def full_text(self) -> str:
        if self.ai_powered:
            badge = {
                "openai": "🤖 AI-Powered (OpenAI)",
                "gemini": "🤖 AI-Powered (Gemini)",
            }.get(self.ai_provider, "🤖 AI-Powered")
        else:
            badge = "📊 Rule-Based"
        header = f"**{PERSONA_LABELS.get(self.persona, self.persona.value)}** ({badge})\n\n"
        return f"{header}{self.narrative}{self.disclaimer}"


def get_persona_weights(persona: AdvisorPersona) -> tuple[float, float, float]:
    return PERSONA_WEIGHTS.get(persona, (0.50, 0.30, 0.20))


def explain_integrated(
    analysis: "IntegratedAnalysis",
    persona: AdvisorPersona = AdvisorPersona.BUFFETT,
    daily_target_pct: float = 0.75,
    account_equity: float = 25_000.0,
) -> InstitutionalAdvice:
    """
    Generate persona-based narrative from integrated technical + sentiment + news data.
    """
    from ai.analyst import call_ai_stock

    target_usd = account_equity * daily_target_pct / 100
    target_ctx = (
        f"Reference daily goal: {daily_target_pct}% of ${account_equity:,.0f} account "
        f"(≈ ${target_usd:,.0f}/day) — illustrative only, NOT guaranteed."
    )

    headlines = "\n".join(
        f"  • [{n.sentiment_label}] {n.title[:100]}" for n in analysis.news_headlines[:6]
    ) or "  No recent headlines."

    prompt = f"""{PERSONA_SYSTEM[persona]}

Analyze this stock for an EDUCATIONAL research note. Never give financial advice or trade orders.

Ticker: {analysis.ticker}
Price: ${analysis.price:,.2f}
Technical score: {analysis.technical_score:.0f}/100
Sentiment score: {analysis.sentiment_score:.0f}/100 ({analysis.sentiment_label})
News score: {analysis.news_score:.0f}/100
Composite score: {analysis.composite_score:.0f}/100
Signal context: {analysis.signal}
Volume ratio: {analysis.volume_ratio:.1f}x avg
ATR%: {analysis.atr_pct:.2f}%
Analyst consensus: {analysis.analyst_consensus}

Recent headlines:
{headlines}

Catalysts / risks from news:
{analysis.catalyst_notes or 'None flagged.'}

Technical context:
{analysis.explanation[:400]}

{target_ctx}

Write 3-4 paragraphs:
1. How this stock looks through your persona's lens (quality, risk, fit)
2. How news and sentiment align or conflict with technicals
3. Key risks and what could invalidate the thesis
4. How a {daily_target_pct}% daily target relates to required capital and volatility (educational only)

RULES: Never say buy/sell/place order. Use "data suggests", "historically", "investors might consider".
"""

    text, provider = call_ai_stock(prompt, system=PERSONA_SYSTEM[persona])
    ai_powered = text is not None

    if not text:
        text = _rule_based_narrative(analysis, persona, daily_target_pct, account_equity)
        provider = "rule-based"

    return InstitutionalAdvice(
        persona=persona,
        ticker=analysis.ticker,
        narrative=text,
        composite_score=analysis.composite_score,
        technical_score=analysis.technical_score,
        sentiment_score=analysis.sentiment_score,
        news_score=analysis.news_score,
        sentiment_label=analysis.sentiment_label,
        headline_summary=headlines[:500],
        catalyst_summary=analysis.catalyst_notes[:300] if analysis.catalyst_notes else "",
        daily_target_context=target_ctx,
        ai_powered=ai_powered,
        ai_provider=provider,
    )


def explain_batch_summary(
    analyses: List["IntegratedAnalysis"],
    persona: AdvisorPersona,
    daily_target_pct: float,
    account_equity: float,
    top_n: int = 5,
) -> InstitutionalAdvice:
    """Market-wide summary across top integrated picks."""
    if not analyses:
        return InstitutionalAdvice(
            persona=persona, ticker="MARKET", narrative="No analyses available.",
            composite_score=0, technical_score=0, sentiment_score=0, news_score=0,
            sentiment_label="N/A", headline_summary="",
            catalyst_summary="",
        )

    top = analyses[:top_n]
    lines = "\n".join(
        f"  {i+1}. {a.ticker} — composite {a.composite_score:.0f} "
        f"(tech {a.technical_score:.0f}, sent {a.sentiment_score:.0f}, news {a.news_score:.0f})"
        for i, a in enumerate(top)
    )
    target_usd = account_equity * daily_target_pct / 100

    from ai.analyst import call_ai

    prompt = f"""{PERSONA_SYSTEM[persona]}

Educational market briefing — NOT financial advice.

Account: ${account_equity:,.0f} | Daily target reference: {daily_target_pct}% (≈ ${target_usd:,.0f}/day)

Top integrated picks (technical + news + sentiment):
{lines}

Write 2-3 paragraphs summarizing:
- Which names best align with your investment philosophy and why
- Broad sentiment/news themes across these names
- Portfolio-level risks at a {daily_target_pct}% daily goal (highly ambitious — explain realistically)

Never say buy or sell."""

    text, provider = call_ai(prompt, system=PERSONA_SYSTEM[persona])
    ai_powered = text is not None
    if not text:
        text = _rule_batch_summary(top, persona, daily_target_pct, account_equity)
        provider = "rule-based"

    return InstitutionalAdvice(
        persona=persona,
        ticker="TOP PICKS",
        narrative=text,
        composite_score=top[0].composite_score,
        technical_score=top[0].technical_score,
        sentiment_score=top[0].sentiment_score,
        news_score=top[0].news_score,
        sentiment_label=top[0].sentiment_label,
        headline_summary=f"Top: {', '.join(a.ticker for a in top)}",
        catalyst_summary="",
        daily_target_context=f"{daily_target_pct}% ≈ ${target_usd:,.0f}/day on ${account_equity:,.0f}",
        ai_powered=ai_powered,
        ai_provider=provider,
    )


def _rule_based_narrative(
    a: "IntegratedAnalysis",
    persona: AdvisorPersona,
    daily_target_pct: float,
    account_equity: float,
) -> str:
    """Template fallback when AI unavailable."""
    target_usd = account_equity * daily_target_pct / 100
    name = PERSONA_LABELS.get(persona, persona.value)

    align = "aligned" if a.sentiment_score >= 55 and a.technical_score >= 60 else (
        "mixed" if a.sentiment_score >= 45 else "conflicted"
    )

    parts = [
        f"**{name} — Educational View on {a.ticker}**",
        "",
        f"Composite score **{a.composite_score:.0f}/100** blends technicals ({a.technical_score:.0f}), "
        f"sentiment ({a.sentiment_score:.0f}, {a.sentiment_label}), and news ({a.news_score:.0f}). "
        f"Technicals and sentiment appear **{align}**.",
        "",
    ]

    if a.news_headlines:
        parts.append(f"**News:** {len(a.news_headlines)} recent headlines tracked. "
                     f"Analyst consensus: {a.analyst_consensus}.")
        if a.catalyst_notes:
            parts.append(f"**Catalysts:** {a.catalyst_notes[:200]}")

    persona_notes = {
        AdvisorPersona.BUFFETT: "From a value lens, focus on whether the business story in headlines supports durable earnings — not short-term price moves.",
        AdvisorPersona.VANGUARD: "Single-stock exposure should be a small part of a diversified plan; this analysis is one input among many.",
        AdvisorPersona.BLACKROCK: "Consider macro and sector risk alongside this name's technical and sentiment profile.",
        AdvisorPersona.ROBINHOOD: "Volume and momentum scores matter for active traders, but elevated targets increase risk of loss.",
    }
    parts.append(persona_notes.get(persona, "Integrate this data with your overall plan and risk tolerance."))

    if daily_target_pct >= 5:
        parts.append(
            f"\n⚠️ A **{daily_target_pct}%** daily target (≈ ${target_usd:,.0f} on this account) "
            f"is extremely aggressive and is rarely sustainable. Most professional traders target far less."
        )
    else:
        parts.append(
            f"\nA **{daily_target_pct}%** daily reference (≈ ${target_usd:,.0f}) scales linearly with account size — "
            f"not a guarantee of achievable returns."
        )

    return "\n".join(parts)


def _rule_batch_summary(
    top: List["IntegratedAnalysis"],
    persona: AdvisorPersona,
    daily_target_pct: float,
    account_equity: float,
) -> str:
    tickers = ", ".join(a.ticker for a in top[:3])
    return (
        f"**{PERSONA_LABELS.get(persona, '')} — Market Scan Summary**\n\n"
        f"Top integrated candidates: {tickers}. "
        f"Highest composite: {top[0].ticker} at {top[0].composite_score:.0f}/100. "
        f"Sentiment across leaders averages {sum(a.sentiment_score for a in top)/len(top):.0f}/100. "
        f"Daily target reference {daily_target_pct}% ≈ ${account_equity * daily_target_pct / 100:,.0f} — educational only."
    )


# Daily target presets for UI
DAILY_TARGET_PRESETS = {
    "Conservative 0.75%": 0.75,
    "Moderate 1%": 1.0,
    "Active 3%": 3.0,
    "Aggressive 5%": 5.0,
    "High 10%": 10.0,
    "Very High 15%": 15.0,
    "Extreme 20%": 20.0,
    "Custom": -1.0,
}


def scale_target_table(equity: float, pcts: Optional[List[float]] = None) -> List[dict]:
    """Show how multiple target %s scale for an account."""
    pcts = pcts or [0.75, 1, 3, 5, 10, 15, 20]
    return [
        {
            "Target %": f"{p}%",
            "Daily $": f"${equity * p / 100:,.0f}",
            "Monthly (~20d)": f"${equity * p / 100 * 20:,.0f}",
        }
        for p in pcts
    ]

"""
AI Analyst — three-tier AI engine for stock analysis explanations.

Tiers (auto-selected in priority order)
----------------------------------------
Tier 1 — OpenAI ChatGPT  : set OPENAI_API_KEY in .env  (GPT-4o-mini by default)
Tier 2 — Google Gemini   : set GEMINI_API_KEY in .env  (gemini-1.5-flash, free)
Tier 3 — Rule-based      : always available, no API key needed

Hard safety rules (NEVER violated regardless of tier):
  1. Analyst ONLY explains — never places orders, never overrides risk manager.
  2. Every response appends mandatory disclaimer.
  3. is_actionable is ALWAYS False.
  4. No "buy now", "sell now", "place an order" language permitted.
  5. AI cannot approve trade proposals — only human can approve.

Usage:
    from ai.analyst import explain_stock_analysis, explain_sentiment_context
    result = explain_stock_analysis(analysis, sentiment=sent_result)
    result.full_text        # full text with AI badge + disclaimer
    result.ai_powered       # True if real AI was used
    result.ai_provider      # "openai" | "gemini" | "rule-based"
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING

import pandas as pd

from trading.strategies import SignalResult

if TYPE_CHECKING:
    from analysis.stock_analyzer import StockAnalysis
    from analysis.stock_ranker import RankedStock
    from analysis.sentiment_analyzer import SentimentResult
    from analysis.market_scanner import ScanResult

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n---\n"
    "⚠️ **NOT FINANCIAL ADVICE.** This is an AI-generated educational explanation only. "
    "It does not constitute a recommendation to buy or sell any security. "
    "Day trading involves significant risk of loss. "
    "Past indicator patterns do not guarantee future results. "
    "Always consult a qualified financial advisor before making investment decisions."
)

_ACTIONABLE_RE = re.compile(
    r"\b(you should (?:buy|sell)|buy (?:now|immediately|today)|sell (?:now|immediately|today)|"
    r"place (?:an? )?order|execute (?:a )?trade|enter (?:a )?(?:long|short))\b",
    re.IGNORECASE,
)

# ── OpenAI client (lazy init) ─────────────────────────────────────────────────
_openai_client = None
_OPENAI_AVAILABLE = False
_OPENAI_MODEL = "gpt-4o-mini"   # cheapest capable model; override via OPENAI_MODEL env var


def _init_openai() -> bool:
    """Initialize OpenAI client. Returns True if OPENAI_API_KEY is set and library available."""
    global _openai_client, _OPENAI_AVAILABLE, _OPENAI_MODEL
    if _OPENAI_AVAILABLE:
        return True
    try:
        import openai
        try:
            from config.settings import get_settings
            s = get_settings()
            api_key = s.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
            if s.OPENAI_MODEL:
                _OPENAI_MODEL = s.OPENAI_MODEL
        except Exception:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return False
        _openai_client = openai.OpenAI(api_key=api_key)
        _OPENAI_MODEL = os.environ.get("OPENAI_MODEL", _OPENAI_MODEL)
        _OPENAI_AVAILABLE = True
        logger.info("OpenAI initialized (model=%s)", _OPENAI_MODEL)
        return True
    except Exception as e:
        logger.debug("OpenAI init failed: %s", e)
        return False


def _call_openai(prompt: str, system: Optional[str] = None, max_tokens: int = 1200) -> Optional[str]:
    """Call OpenAI Chat Completions. Returns text or None on failure."""
    if not _init_openai() or _openai_client is None:
        return None
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = _openai_client.chat.completions.create(
            model=_OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        return _sanitize(text.strip()) if text.strip() else None
    except Exception as e:
        logger.debug("OpenAI call failed: %s", e)
        return None


# ── Gemini client (lazy init) ──────────────────────────────────────────────────
_gemini_client = None
_gemini_model = None
_GEMINI_AVAILABLE = False


def _init_gemini() -> bool:
    """Initialize Gemini client. Returns True if successful."""
    global _gemini_client, _gemini_model, _GEMINI_AVAILABLE
    if _GEMINI_AVAILABLE:
        return True
    try:
        import google.generativeai as genai
        try:
            from config.settings import get_settings
            s = get_settings()
            api_key = (
                s.GEMINI_API_KEY
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY", "")
            )
        except Exception:
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return False
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 800,
                "top_p": 0.8,
            },
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        )
        _GEMINI_AVAILABLE = True
        logger.info("Gemini AI initialized (gemini-1.5-flash)")
        return True
    except Exception as e:
        logger.debug("Gemini init failed: %s", e)
        return False


def _ai_provider_preference() -> str:
    """Return configured provider preference: auto, openai, or gemini."""
    try:
        from config.settings import get_settings
        return (get_settings().AI_PROVIDER or "auto").lower().strip()
    except Exception:
        return "auto"


def get_active_ai_provider() -> str:
    """Return default AI provider (Gemini across the board when configured)."""
    pref = _ai_provider_preference()
    if pref == "gemini" and _init_gemini():
        return "gemini"
    if pref == "openai" and _init_openai():
        return "openai"
    if pref == "auto":
        if _init_gemini():
            return "gemini"
        if _init_openai():
            return "openai"
    return "rule-based"


def is_ai_available() -> bool:
    """Return True if OpenAI or Gemini is configured."""
    return get_active_ai_provider() != "rule-based"


def call_ai(prompt: str, system: Optional[str] = None) -> tuple[Optional[str], str]:
    """
    General AI — Gemini first across the board (market summaries, batch, general chat).
    Returns (response_text, provider_name).
    """
    pref = _ai_provider_preference()
    order = ["gemini", "openai"] if pref in ("gemini", "auto") else [pref, "gemini" if pref == "openai" else "openai"]

    for provider in order:
        if provider == "gemini":
            full = f"{system}\n\n{prompt}" if system else prompt
            text = _call_gemini(full)
            if text:
                return text, "gemini"
        elif provider == "openai":
            text = _call_openai(prompt, system=system)
            if text:
                return text, "openai"
    return None, "rule-based"


def _call_ai(prompt: str, system: Optional[str] = None) -> Optional[str]:
    """Backward-compatible: returns text only."""
    text, _ = call_ai(prompt, system=system)
    return text


def is_ai_available_legacy_gemini() -> bool:
    return _init_gemini()


def _sanitize(text: str) -> str:
    original = text
    text = _ACTIONABLE_RE.sub("[signal context]", text)
    if text != original:
        logger.warning("AI analyst: stripped actionable language")
    return text


def _call_gemini(prompt: str, max_output_tokens: int = 800) -> Optional[str]:
    """Call Gemini API. Returns text or None on failure."""
    if not _init_gemini():
        return None
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": max_output_tokens,
                "top_p": 0.8,
            },
        )
        response = model.generate_content(prompt)
        return _sanitize(response.text.strip())
    except Exception as e:
        logger.debug("Gemini call failed: %s", e)
        return None


def _scan_provider_pref() -> str:
    try:
        from config.settings import get_settings
        return (get_settings().AI_SCAN_PROVIDER or "gemini").lower().strip()
    except Exception:
        return "gemini"


def _stock_provider_pref() -> str:
    try:
        from config.settings import get_settings
        s = get_settings()
        return (s.AI_STOCK_PROVIDER or s.AI_DEEP_PROVIDER or "openai").lower().strip()
    except Exception:
        return "openai"


def call_ai_stock(prompt: str, system: Optional[str] = None) -> tuple[Optional[str], str]:
    """
    Per-stock deep analysis — ChatGPT (paid) by default.
    Use for: AI Summary, single-ticker chat, research notes, explain_stock_analysis.
    """
    pref = _stock_provider_pref()
    order = ["openai", "gemini"] if pref == "openai" else (
        ["gemini", "openai"] if pref == "gemini" else ["openai", "gemini"]
    )
    for provider in order:
        if provider == "openai":
            text = _call_openai(prompt, system=system, max_tokens=1200)
            if text:
                return text, "openai"
        elif provider == "gemini":
            full = f"{system}\n\n{prompt}" if system else prompt
            text = _call_gemini(full, max_output_tokens=1000)
            if text:
                return text, "gemini"
    return None, "rule-based"


def call_ai_deep(prompt: str, system: Optional[str] = None) -> tuple[Optional[str], str]:
    """Alias for call_ai_stock — per-stock ChatGPT analysis."""
    return call_ai_stock(prompt, system=system)


def call_ai_scan(prompt: str, system: Optional[str] = None) -> tuple[Optional[str], str]:
    """
    Lightweight bulk scan notes — Gemini by default (~1 call per scan).
    Set AI_SCAN_PROVIDER=off to disable.
    """
    pref = _scan_provider_pref()
    if pref in ("off", "none", "false", "0"):
        return None, "rule-based"

    full = f"{system}\n\n{prompt}" if system else prompt
    order = ["gemini", "openai"] if pref == "gemini" else (
        ["openai", "gemini"] if pref == "openai" else ["gemini", "openai"]
    )
    for provider in order:
        if provider == "gemini":
            text = _call_gemini(full, max_output_tokens=600)
            if text:
                return text, "gemini"
        elif provider == "openai":
            text = _call_openai(prompt, system=system, max_tokens=600)
            if text:
                return text, "openai"
    return None, "rule-based"


def is_gemini_available() -> bool:
    return _init_gemini()


def is_openai_available() -> bool:
    return _init_openai()


# ── Response dataclass ─────────────────────────────────────────────────────────

@dataclass
class AnalystResponse:
    """Structured AI analyst output. is_actionable is ALWAYS False."""
    explanation: str
    disclaimer: str = _DISCLAIMER
    is_actionable: bool = False
    confidence_narrative: str = ""
    ai_powered: bool = False
    ai_provider: str = "rule-based"

    @property
    def full_text(self) -> str:
        if self.ai_powered:
            badge = {
                "openai": "🤖 **AI-Powered Analysis (OpenAI ChatGPT)**",
                "gemini": "🤖 **AI-Powered Analysis (Google Gemini)**",
            }.get(self.ai_provider, "🤖 **AI-Powered Analysis**")
        else:
            badge = "📊 **Rule-Based Analysis**"
        return f"{badge}\n\n{self.explanation}{self.disclaimer}"


_STOCK_SYSTEM = (
    "You are a stock market educational AI assistant. Explain technical and sentiment data "
    "to help users understand market conditions. You NEVER give financial advice, never tell "
    "users to buy or sell, and always note that results are not guaranteed."
)


def _stock_prompt(analysis: "StockAnalysis", sentiment: Optional["SentimentResult"] = None) -> str:
    """Build ChatGPT/Gemini prompt for single-stock educational analysis."""
    ind = analysis.indicators
    sent_block = ""
    if sentiment and sentiment.is_valid:
        sent_block = f"""
Sentiment Context:
- News sentiment: {sentiment.news_sentiment_label} ({sentiment.news_sentiment_score:.0f}/100)
- Analyst consensus: {sentiment.analyst_recommendation} ({sentiment.num_analyst_opinions} analysts)
- Analyst price target: ${sentiment.analyst_target_price:,.2f} ({sentiment.price_vs_target_pct:+.1f}% upside) if available
- 52-week position: {sentiment.price_vs_52w_high_pct:+.1f}% from 52w high
- Short interest ratio: {sentiment.short_ratio if sentiment.short_ratio else 'N/A'}
- Earnings growth YoY: {f'{sentiment.earnings_growth*100:.1f}%' if sentiment.earnings_growth else 'N/A'}
- Broad market: {sentiment.market_trend}
- Recent catalysts: {sentiment.catalyst_notes[:300]}
"""

    return f"""Stock: {analysis.ticker}
Current Price: ${analysis.current_price:,.2f}
Signal: {analysis.signal} (Overall Score: {analysis.overall_score:.0f}/100)
Risk Score: {analysis.risk_score:.0f}/100
Confidence: {analysis.confidence:.0f}/100

Technical Indicators:
- RSI(14): {ind.get('rsi', 'N/A')}
- MACD Histogram: {ind.get('macd_hist', 'N/A')}
- SMA20: {ind.get('sma_20', 'N/A')}
- SMA50: {ind.get('sma_50', 'N/A')}
- Bollinger Band position: {ind.get('bb_position', 'N/A')}
- Volume Ratio: {ind.get('volume_ratio', 'N/A')}
- ATR%: {ind.get('atr_pct', 'N/A')}
- Trend Score: {analysis.trend_score:.0f}/100
- Momentum Score: {analysis.momentum_score:.0f}/100
- Volume Score: {analysis.volume_score:.0f}/100

Rule-engine levels (NOT personalized advice):
- Stop-loss: ${analysis.stop_loss_price:,.2f}
- Take-profit: ${analysis.take_profit_price:,.2f}
- Support: ${analysis.support_level:,.2f}
- Resistance: ${analysis.resistance_level:,.2f}
- Timeframe bias: {analysis.timeframe_bias}
{sent_block}
Strategy summary: {analysis.reason_summary[:300]}

Provide a 3-4 paragraph educational explanation that:
1. Explains what the technical indicators say about this stock's current pattern
2. Notes key risk factors and what could invalidate the signal
3. If sentiment data is available, explain how news/analyst sentiment aligns or conflicts with technicals
4. Mentions what a day trader should watch (volume, levels, catalysts)

RULES:
- Never say "you should buy" or "you should sell" — use "the pattern suggests" or "technically"
- Never guarantee profit
- Keep the tone educational and data-driven
- Be concise (3-4 paragraphs max)
"""


def _scan_prompt(scan_result: "ScanResult", sentiment: Optional["SentimentResult"] = None) -> str:
    """Build prompt for day-trading scan result explanation."""
    sent_block = ""
    if sentiment and sentiment.is_valid:
        sent_block = f"""
Sentiment:
- News: {sentiment.news_sentiment_label} ({sentiment.news_sentiment_score:.0f}/100)
- Analyst: {sentiment.analyst_recommendation} | Target: ${sentiment.analyst_target_price or 'N/A'}
- Market: {sentiment.market_trend} | Catalysts: {sentiment.catalyst_notes[:200]}
"""

    return f"""Explain why {scan_result.ticker} appeared in today's market scan for day trading candidates. Be educational and objective. Never guarantee profit. Never say "buy now" or "sell now".

Scanner data for {scan_result.ticker}:
- Price: ${scan_result.price:,.2f}
- 1-day change: {scan_result.change_pct_1d:+.2f}%
- 5-day change: {scan_result.change_pct_5d:+.2f}%
- Volume ratio vs 20-day avg: {scan_result.volume_ratio:.2f}x
- RSI: {scan_result.rsi:.1f}
- MACD histogram: {scan_result.macd_hist:.4f}
- ATR (daily range%): {scan_result.atr_pct:.2f}%
- Gap at open: {scan_result.gap_pct:+.2f}%
- Volume score: {scan_result.volume_score:.0f}/100
- Momentum score: {scan_result.momentum_score:.0f}/100
- RSI zone score: {scan_result.rsi_score:.0f}/100
- Trend score: {scan_result.trend_score:.0f}/100
- Overall day-trading score: {scan_result.overall_score:.1f}/100
- Signal: {scan_result.signal}
- Rule-engine stop-loss: ${scan_result.stop_loss_price:,.2f}
- Rule-engine take-profit: ${scan_result.take_profit_price:,.2f}
{sent_block}

Write 2-3 paragraphs explaining:
1. Why this stock has a high day-trading score today (what signals are aligned)
2. Key risk factors a trader should be aware of
3. How sentiment/news context supports or conflicts with the technical pattern
"""


def _sentiment_prompt(sentiment: "SentimentResult") -> str:
    """Build prompt for sentiment-only explanation."""
    headlines_block = "\n".join(
        [f"  - [{n.sentiment_label}] {n.title[:100]} ({n.source}, {n.published})"
         for n in sentiment.news_items[:8]]
    ) or "  No recent headlines found."

    return f"""Explain the sentiment picture for {sentiment.ticker} to help a trader understand market mood. Never give financial advice. Never say buy or sell.

Ticker: {sentiment.ticker}
Overall sentiment score: {sentiment.overall_sentiment_score:.0f}/100 — {sentiment.overall_sentiment_label}
News sentiment: {sentiment.news_sentiment_label} ({sentiment.news_sentiment_score:.0f}/100)
Analyst consensus: {sentiment.analyst_recommendation} ({sentiment.num_analyst_opinions} analysts)
Analyst price target: {'${:.2f} ({:+.1f}% from current)'.format(sentiment.analyst_target_price, sentiment.price_vs_target_pct) if sentiment.analyst_target_price else 'N/A'}
52-week position: {sentiment.price_vs_52w_high_pct:+.1f}% from high / ${sentiment.week_52_low or 'N/A'} - ${sentiment.week_52_high or 'N/A'}
Beta: {sentiment.beta or 'N/A'}
Short interest ratio: {sentiment.short_ratio or 'N/A'} days to cover
Earnings growth YoY: {f'{sentiment.earnings_growth*100:.1f}%' if sentiment.earnings_growth else 'N/A'}
Revenue growth YoY: {f'{sentiment.revenue_growth*100:.1f}%' if sentiment.revenue_growth else 'N/A'}
Broad market: {sentiment.market_trend} (5-day SPY volatility proxy: {sentiment.vix_proxy:.1f}%)

Recent headlines ({len(sentiment.news_items)} total):
{headlines_block}

Detected catalysts:
{sentiment.catalyst_notes}

Explain in 2-3 paragraphs:
1. What the overall sentiment picture looks like and why
2. Any notable catalysts or risk events from the headlines
3. How the fundamental data supports or contradicts the sentiment
"""


def _compare_prompt(ranked_stocks: list) -> str:
    """Build prompt comparing top two ranked stocks."""
    top = ranked_stocks[0].analysis
    second = ranked_stocks[1].analysis

    return f"""Compare these two stocks from a technical analysis perspective. Never guarantee returns. Never say buy or sell.

Stock 1: {top.ticker} — Score {top.overall_score:.0f}/100, Signal: {top.signal}
- Trend: {top.trend_score:.0f} | Momentum: {top.momentum_score:.0f} | Risk: {top.risk_score:.0f}
- RSI: {top.indicators.get('rsi','N/A')} | ATR%: {top.indicators.get('atr_pct','N/A')}

Stock 2: {second.ticker} — Score {second.overall_score:.0f}/100, Signal: {second.signal}
- Trend: {second.trend_score:.0f} | Momentum: {second.momentum_score:.0f} | Risk: {second.risk_score:.0f}
- RSI: {second.indicators.get('rsi','N/A')} | ATR%: {second.indicators.get('atr_pct','N/A')}

In 2 paragraphs, explain why {top.ticker} ranks higher than {second.ticker} based on the technical indicators, and what risk factors each carries.
"""


# ── Public API ─────────────────────────────────────────────────────────────────

def explain_signal(signal: SignalResult, df: Optional[pd.DataFrame] = None) -> str:
    """Explain a strategy signal. Returns full_text string."""
    try:
        return _build_signal_explanation(signal, df).full_text
    except Exception as e:
        return f"Signal: {signal.signal.value} | {signal.strategy}\n\n{_DISCLAIMER}"


def explain_signal_structured(signal: SignalResult, df: Optional[pd.DataFrame] = None) -> AnalystResponse:
    """Return AnalystResponse for a strategy signal."""
    try:
        return _build_signal_explanation(signal, df)
    except Exception as e:
        return AnalystResponse(explanation=f"Error: {e}")


def explain_stock_analysis(
    analysis: "StockAnalysis",
    sentiment: Optional["SentimentResult"] = None,
) -> AnalystResponse:
    """
    Explain a StockAnalysis with optional sentiment enrichment.
    Uses Gemini AI if GEMINI_API_KEY is configured, else rule-based.
    """
    try:
        text, provider = call_ai_stock(_stock_prompt(analysis, sentiment), system=_STOCK_SYSTEM)
        if text:
            return AnalystResponse(
                explanation=text,
                ai_powered=True,
                ai_provider=provider,
                confidence_narrative=f"Indicator confidence: {analysis.confidence:.0f}/100",
            )
        return _rule_explain_stock(analysis, sentiment)
    except Exception as e:
        logger.error("explain_stock_analysis error: %s", e)
        return AnalystResponse(explanation=f"Analysis explanation unavailable: {e}")


def explain_scan_result(
    scan_result: "ScanResult",
    sentiment: Optional["SentimentResult"] = None,
) -> AnalystResponse:
    """
    Explain a MarketScanner ScanResult with optional sentiment.
    """
    try:
        text, provider = call_ai(_scan_prompt(scan_result, sentiment))
        if text:
            return AnalystResponse(explanation=text, ai_powered=True, ai_provider=provider)
        return _rule_explain_scan(scan_result, sentiment)
    except Exception as e:
        return AnalystResponse(explanation=f"Unavailable: {e}")


def explain_sentiment_context(sentiment: "SentimentResult") -> AnalystResponse:
    """
    Provide an AI narrative of the sentiment data for a stock.
    """
    try:
        text, provider = call_ai_stock(_sentiment_prompt(sentiment))
        if text:
            return AnalystResponse(explanation=text, ai_powered=True, ai_provider=provider)
        return _rule_explain_sentiment(sentiment)
    except Exception as e:
        return AnalystResponse(explanation=f"Sentiment explanation unavailable: {e}")


def explain_ranking_comparison(ranked_stocks: list) -> str:
    """Compare top 2 ranked stocks. Returns full text."""
    if not ranked_stocks or len(ranked_stocks) < 2:
        return f"Only one ticker — no comparison available.{_DISCLAIMER}"
    try:
        text, provider = call_ai(_compare_prompt(ranked_stocks))
        if text:
            return AnalystResponse(explanation=text, ai_powered=True, ai_provider=provider).full_text
        return _rule_compare(ranked_stocks).full_text
    except Exception as e:
        return f"Comparison unavailable: {e}{_DISCLAIMER}"


# ── Gemini implementations (thin wrappers — prompts live above) ────────────────

def _gemini_explain_stock(analysis: "StockAnalysis", sentiment: Optional["SentimentResult"]) -> AnalystResponse:
    """Use Gemini to explain a StockAnalysis."""
    response_text = _call_gemini(f"{_STOCK_SYSTEM}\n\n{_stock_prompt(analysis, sentiment)}")
    if not response_text:
        return _rule_explain_stock(analysis, sentiment)
    return AnalystResponse(
        explanation=response_text,
        ai_powered=True,
        confidence_narrative=f"Indicator confidence: {analysis.confidence:.0f}/100",
    )


def _gemini_explain_scan(scan_result: "ScanResult", sentiment: Optional["SentimentResult"]) -> AnalystResponse:
    """Use Gemini to explain a scanner result."""
    text = _call_gemini(_scan_prompt(scan_result, sentiment))
    if not text:
        return _rule_explain_scan(scan_result, sentiment)
    return AnalystResponse(explanation=text, ai_powered=True)


def _gemini_explain_sentiment(sentiment: "SentimentResult") -> AnalystResponse:
    """Use Gemini to explain sentiment data."""
    text = _call_gemini(_sentiment_prompt(sentiment))
    if not text:
        return _rule_explain_sentiment(sentiment)
    return AnalystResponse(explanation=text, ai_powered=True)


def _gemini_compare(ranked_stocks: list) -> AnalystResponse:
    """Use Gemini to compare top 2 ranked stocks."""
    text = _call_gemini(_compare_prompt(ranked_stocks))
    if not text:
        return _rule_compare(ranked_stocks)
    return AnalystResponse(explanation=text, ai_powered=True)


# ── Rule-based fallbacks ───────────────────────────────────────────────────────

def _rule_explain_stock(analysis: "StockAnalysis", sentiment: Optional["SentimentResult"]) -> AnalystResponse:
    """Template-based explanation without AI."""
    sig = analysis.signal
    tf = analysis.timeframe_bias.replace("_", "-")
    ind = analysis.indicators
    rsi = ind.get("rsi")

    parts = [
        f"**Technical Analysis — {analysis.ticker}**",
        f"Signal: **{sig}** | Price: ${analysis.current_price:,.2f} | Score: {analysis.overall_score:.0f}/100",
        "",
    ]

    # Signal frame
    frames = {
        "BUY_CANDIDATE": f"{analysis.ticker} is ranked as a higher candidate based on aligned bullish indicators. This does not guarantee price will rise.",
        "SELL_CANDIDATE": f"{analysis.ticker} shows technically weak patterns. This does not predict continued decline.",
        "WATCH": f"{analysis.ticker} shows mixed signals. Conditions may clarify in upcoming sessions.",
        "AVOID": f"{analysis.ticker} shows elevated risk or weak structure. Consider monitoring rather than entering.",
    }
    parts.append(frames.get(sig, f"Signal: {sig}."))

    # Indicators
    if rsi is not None:
        zone = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
        parts.append(f"\nRSI is {rsi:.1f} ({zone}).")
    macd_hist = ind.get("macd_hist")
    if macd_hist is not None:
        direction = "bullish" if macd_hist > 0 else "bearish"
        parts.append(f"MACD histogram is {macd_hist:.4f} ({direction} momentum).")

    # Timeframe
    tf_notes = {
        "short-term": "Indicators suggest a short-term bias (days to 1-2 weeks).",
        "swing": "Indicators suggest a swing-trade bias (1-4 weeks).",
        "long-term": "Price is above long-term SMA(200), suggesting longer-term bullish structure.",
    }
    parts.append(tf_notes.get(tf, "Timeframe is unclear from current indicators."))

    # Risk
    risk = analysis.risk_score
    risk_level = "HIGH" if risk >= 70 else "MODERATE" if risk >= 50 else "LOW"
    parts.append(f"\nRisk score: {risk:.0f}/100 ({risk_level}).")

    # Levels
    parts.append(
        f"\nRule-engine levels: Stop-loss ${analysis.stop_loss_price:,.2f} | "
        f"Take-profit ${analysis.take_profit_price:,.2f}. These are illustrative — not personalized advice."
    )

    # Sentiment block
    if sentiment and sentiment.is_valid:
        parts.append(
            f"\n**Sentiment:** {sentiment.overall_sentiment_label} ({sentiment.overall_sentiment_score:.0f}/100). "
            f"News: {sentiment.news_sentiment_label} | Analyst: {sentiment.analyst_recommendation}. "
            f"Market is {sentiment.market_trend}."
        )

    return AnalystResponse(
        explanation="\n".join(parts),
        ai_powered=False,
        confidence_narrative=f"Confidence: {analysis.confidence:.0f}/100",
    )


def _rule_explain_scan(result: "ScanResult", sentiment: Optional["SentimentResult"]) -> AnalystResponse:
    """Template explanation for scanner result."""
    parts = [
        f"**Day Trading Analysis — {result.ticker}**",
        f"Score: {result.overall_score:.1f}/100 | Signal: {result.signal} | Price: ${result.price:,.2f}",
        "",
        f"Volume is {result.volume_ratio:.1f}x the 20-day average — {'significant unusual activity' if result.volume_ratio >= 2 else 'above-normal participation'}.",
        f"1-day change: {result.change_pct_1d:+.2f}% | 5-day: {result.change_pct_5d:+.2f}%.",
        f"RSI: {result.rsi:.1f} | MACD: {'bullish' if result.macd_hist > 0 else 'bearish'}.",
        f"Daily range (ATR): {result.atr_pct:.2f}% — {'good for day trading' if 1.5 <= result.atr_pct <= 4 else 'limited range' if result.atr_pct < 1.5 else 'high volatility, size carefully'}.",
    ]
    if result.gap_pct and abs(result.gap_pct) >= 0.5:
        parts.append(f"Gap at open: {result.gap_pct:+.2f}% — {'breakout setup' if result.gap_pct > 0 else 'gap-down, watch support'}.")

    if sentiment and sentiment.is_valid:
        parts.append(f"\nSentiment: {sentiment.overall_sentiment_label} ({sentiment.overall_sentiment_score:.0f}/100). Analyst: {sentiment.analyst_recommendation}.")

    return AnalystResponse(explanation="\n".join(parts), ai_powered=False)


def _rule_explain_sentiment(sentiment: "SentimentResult") -> AnalystResponse:
    """Template explanation for sentiment data."""
    parts = [
        f"**Sentiment Analysis — {sentiment.ticker}**",
        f"Overall: **{sentiment.overall_sentiment_label}** ({sentiment.overall_sentiment_score:.0f}/100)",
        "",
        sentiment.sentiment_summary,
        "",
        f"**Catalysts:** {sentiment.catalyst_notes}",
    ]
    return AnalystResponse(explanation="\n".join(parts), ai_powered=False)


def _rule_compare(ranked_stocks: list) -> AnalystResponse:
    """Template comparison of top 2 stocks."""
    top = ranked_stocks[0].analysis
    second = ranked_stocks[1].analysis
    diff = top.overall_score - second.overall_score

    parts = [
        f"**Ranking Comparison: {top.ticker} vs {second.ticker}**",
        "",
        f"{top.ticker} ranks higher with {top.overall_score:.0f}/100 vs {second.ticker}'s {second.overall_score:.0f}/100 (difference: {diff:.0f} pts).",
    ]

    if top.trend_score - second.trend_score > 5:
        parts.append(f"Trend: {top.ticker} has stronger trend alignment ({top.trend_score:.0f} vs {second.trend_score:.0f}).")
    if top.momentum_score - second.momentum_score > 5:
        parts.append(f"Momentum: {top.ticker} shows stronger momentum ({top.momentum_score:.0f} vs {second.momentum_score:.0f}).")
    if second.risk_score - top.risk_score > 5:
        parts.append(f"Risk: {top.ticker} carries lower risk score ({top.risk_score:.0f} vs {second.risk_score:.0f}).")

    parts.append("\nThis comparison is based on technical indicators only and does not predict future returns.")
    return AnalystResponse(explanation="\n".join(parts), ai_powered=False)


def _build_signal_explanation(signal: SignalResult, df: Optional[pd.DataFrame]) -> AnalystResponse:
    """Build rule-based explanation for a strategy signal."""
    sig_val = signal.signal.value if hasattr(signal.signal, "value") else str(signal.signal)
    conf = int((signal.confidence if signal.confidence <= 1.0 else signal.confidence / 100) * 100)

    conf_narrative = (
        f"High confidence ({conf}%) — multiple signals converge." if conf >= 75 else
        f"Moderate confidence ({conf}%) — some signals mixed." if conf >= 50 else
        f"Low confidence ({conf}%) — conditions unclear."
    )

    parts = [f"**Strategy: {signal.strategy}** | Signal: **{sig_val}**", "", signal.explanation or ""]
    if df is not None and not df.empty:
        row = df.iloc[-1]
        if "rsi" in df.columns and not pd.isna(row.get("rsi")):
            rsi = float(row["rsi"])
            parts.append(f"RSI(14): {rsi:.1f} ({'overbought' if rsi > 70 else 'oversold' if rsi < 30 else 'neutral'})")

    parts += ["", conf_narrative]

    if sig_val == "BUY":
        parts.append("Historical BUY patterns in backtests have been associated with upward movement. This does not guarantee future results.")
    elif sig_val == "SELL":
        parts.append("Historical SELL patterns have been associated with downward pressure. Past patterns do not predict future results.")

    return AnalystResponse(
        explanation=_sanitize("\n".join(parts)),
        confidence_narrative=conf_narrative,
        ai_powered=False,
    )

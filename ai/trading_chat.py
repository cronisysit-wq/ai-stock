"""
Trading Chat — conversational Q&A about stocks and trading concepts.

Uses OpenAI/Gemini via ai.analyst.call_ai with live technical + sentiment context.
Educational only — never places orders or gives actionable trade instructions.

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "\n\n---\n"
    "⚠️ **NOT FINANCIAL ADVICE.** Educational AI only. "
    "This chat cannot place orders or override risk rules."
)

_SYSTEM = """You are an educational trading research assistant in a paper-trading app.

RULES (never break):
- Explain markets, stocks, indicators, sentiment, and risk in plain English.
- NEVER say "buy now", "sell now", "place an order", or guarantee profits.
- Use phrases like "data suggests", "historically", "investors often consider".
- When stock data is provided below, reference specific numbers from it.
- For general questions (no ticker), teach concepts clearly.
- Keep answers concise (2–4 short paragraphs unless user asks for deep dive).
- If you don't know, say so — do not invent prices or news."""

_TICKER_RE = re.compile(r"\$?([A-Z]{1,5})\b")
_COMMON_WORDS = frozenset({
    "I", "A", "AI", "US", "UK", "EU", "ETF", "IPO", "CEO", "CFO", "GDP", "FED",
    "SEC", "NYSE", "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN",
    "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "DAY", "GET", "HAS", "HIM", "HIS",
    "HOW", "ITS", "MAY", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID",
    "LET", "PUT", "SAY", "SHE", "TOO", "USE", "WHY", "RSI", "MACD", "ATR", "VIX",
    "PE", "EPS", "ROI", "ROE", "YOY", "QOQ", "API", "KEY", "FAQ",
    "TELL", "ME", "ABOUT", "WHAT", "WHEN", "WITH", "FROM", "THAT", "THIS",
    "STOCK", "TRADE", "CHAT", "GOOD", "BEST", "WATCH", "AVOID", "BUY", "SELL",
    "APPLE", "AMAZON", "GOOGLE", "TESLA", "IS", "RSI",
})


@dataclass
class ChatMessage:
    role: str  # user | assistant
    content: str


@dataclass
class ChatResponse:
    reply: str
    ai_powered: bool = False
    ai_provider: str = "rule-based"
    tickers_used: List[str] = field(default_factory=list)
    is_actionable: bool = False

    @property
    def full_text(self) -> str:
        return f"{self.reply}{_DISCLAIMER}"


def extract_tickers(text: str, focus_ticker: Optional[str] = None) -> List[str]:
    """Pull likely ticker symbols from user message (whole words only)."""
    found: List[str] = []
    if focus_ticker:
        t = focus_ticker.strip().upper()
        if t and t not in _COMMON_WORDS:
            found.append(t)

    upper = text.upper()
    for m in re.finditer(r"\$([A-Z]{1,5})\b", upper):
        sym = m.group(1)
        if sym not in _COMMON_WORDS and sym not in found:
            found.append(sym)

    for word in re.split(r"[^A-Za-z]+", text):
        w = word.upper()
        if 2 <= len(w) <= 5 and w.isalpha() and w not in _COMMON_WORDS and w not in found:
            found.append(w)

    return found[:3]


def _gather_stock_context(ticker: str) -> str:
    """Fetch technical + sentiment snapshot for one ticker."""
    lines = [f"=== {ticker} ==="]
    try:
        from analysis.stock_analyzer import StockAnalyzer
        from analysis.sentiment_analyzer import SentimentAnalyzer
        from trading.market_data import get_live_quote

        tech = StockAnalyzer().analyze(ticker)
        quote = get_live_quote(ticker)
        price = quote.get("price") or tech.current_price
        src = quote.get("source", "unknown")

        if tech.error:
            lines.append(f"Technical: unavailable ({tech.error})")
        else:
            lines.append(
                f"Price: ${price:,.2f} ({src}) | Signal: {tech.signal} | "
                f"Overall score: {tech.overall_score:.0f}/100 | "
                f"Trend: {tech.trend_score:.0f} | Momentum: {tech.momentum_score:.0f} | "
                f"Risk: {tech.risk_score:.0f}"
            )
            lines.append(f"Stop (ref): ${tech.stop_loss_price:,.2f} | Target (ref): ${tech.take_profit_price:,.2f}")
            if tech.reason_summary:
                lines.append(f"Technical note: {tech.reason_summary[:400]}")

        sent = SentimentAnalyzer(max_news=6).analyze(ticker, current_price=price or 0)
        if sent.is_valid:
            headlines = "; ".join(n.title[:80] for n in sent.news_items[:4])
            lines.append(
                f"Sentiment: {sent.overall_sentiment_label} ({sent.overall_sentiment_score:.0f}/100) | "
                f"News: {sent.news_sentiment_score:.0f} | Analyst: {sent.analyst_recommendation} | "
                f"Sector: {sent.sector}"
            )
            if headlines:
                lines.append(f"Recent headlines: {headlines}")
        else:
            lines.append("Sentiment: unavailable")
    except Exception as exc:
        lines.append(f"Data error: {exc}")
    return "\n".join(lines)


def _format_history(history: List[ChatMessage], max_turns: int = 6) -> str:
    if not history:
        return ""
    recent = history[-max_turns:]
    parts = []
    for msg in recent:
        label = "User" if msg.role == "user" else "Assistant"
        parts.append(f"{label}: {msg.content[:600]}")
    return "\n".join(parts)


def _rule_reply(message: str, tickers: List[str], context: str) -> str:
    """Fallback when no AI key configured."""
    if tickers and context:
        return (
            f"I can see data for **{', '.join(tickers)}** but AI is not configured.\n\n"
            f"Add `OPENAI_API_KEY` to your `.env` file for full chat answers.\n\n"
            f"**Available data preview:**\n```\n{context[:1200]}\n```"
        )
    return (
        "**Rule-based mode** — add `OPENAI_API_KEY` or `GEMINI_API_KEY` to `.env` for AI chat.\n\n"
        "You can still ask general questions; I'll explain that AI keys unlock personalized "
        "answers with live technical and sentiment data for any ticker (e.g. *What is RSI?* or *Tell me about NVDA*)."
    )


def chat(
    user_message: str,
    history: Optional[List[ChatMessage]] = None,
    focus_ticker: Optional[str] = None,
) -> ChatResponse:
    """
    One chat turn — enriches with stock context when tickers detected.
    """
    from ai.analyst import call_ai, call_ai_stock, _sanitize

    history = history or []
    message = (user_message or "").strip()
    if not message:
        return ChatResponse(reply="Please enter a question.", ai_powered=False)

    tickers = extract_tickers(message, focus_ticker)
    context_blocks = [_gather_stock_context(t) for t in tickers]
    context = "\n\n".join(context_blocks)

    hist_text = _format_history(history)
    prompt_parts = []
    if context:
        prompt_parts.append(f"LIVE STOCK DATA (use these numbers):\n{context}")
    if hist_text:
        prompt_parts.append(f"RECENT CHAT:\n{hist_text}")
    prompt_parts.append(f"USER QUESTION:\n{message}")
    prompt = "\n\n".join(prompt_parts)

    if tickers or focus_ticker:
        text, provider = call_ai_stock(prompt, system=_SYSTEM)
    else:
        text, provider = call_ai(prompt, system=_SYSTEM)
    if text:
        text = _sanitize(text)
        return ChatResponse(
            reply=text,
            ai_powered=True,
            ai_provider=provider,
            tickers_used=tickers,
        )

    return ChatResponse(
        reply=_rule_reply(message, tickers, context),
        ai_powered=False,
        ai_provider="rule-based",
        tickers_used=tickers,
    )

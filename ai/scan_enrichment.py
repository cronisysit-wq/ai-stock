"""
Batch AI enrichment for Strategy Signals scan — token-efficient.

Uses ONE Gemini call per scan for top N picks (default 20), not one call per stock.
Deep follow-up uses call_ai_deep (OpenAI) via Trading Chat / AI Summary.

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from analysis.strategy_sentiment_scanner import StrategySentimentRow

logger = logging.getLogger(__name__)

_SCAN_SYSTEM = """You are an educational stock scanner assistant.
For each ticker, write ONE short sentence (max 22 words) explaining the rank — educational only.
Never say buy now, sell now, or place an order.
Output format — one line per ticker, exactly:
TICKER|your one sentence here"""


def _build_batch_prompt(rows: List["StrategySentimentRow"]) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"{r.ticker}|action={r.suggested_action}|composite={r.composite_score:.0f}|"
            f"strategy={r.strategy_signal}({r.strategy_score:.0f})|"
            f"sentiment={r.sentiment_label}({r.sentiment_score:.0f})|analyst={r.analyst}|"
            f"price=${r.price:,.2f}"
        )
    return (
        "Ranked stock picks (algorithmic scores already computed — add brief educational notes):\n\n"
        + "\n".join(lines)
        + "\n\nRespond with TICKER|note lines only for each ticker above."
    )


def _parse_batch_response(text: str) -> Dict[str, str]:
    notes: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        ticker, _, note = line.partition("|")
        ticker = ticker.strip().upper().lstrip("-•* ")
        note = note.strip()
        if ticker and note and len(ticker) <= 6 and ticker.isalpha():
            notes[ticker] = note
    return notes


def enrich_scan_rows(
    rows: List["StrategySentimentRow"],
    top_n: int = 20,
    enable: bool = True,
) -> tuple[int, str]:
    """
    Add ai_note to top ranked actionable rows via one batch Gemini call.

    Returns (count_updated, provider_used).
    """
    from analysis.strategy_sentiment_scanner import ACTION_AVOID, ACTION_WATCH

    if not enable or not rows:
        return 0, "rule-based"

    try:
        from config.settings import get_settings
        top_n = get_settings().AI_SCAN_TOP_N or top_n
    except Exception:
        pass

    candidates = [
        r for r in rows
        if r.suggested_action not in (ACTION_AVOID, ACTION_WATCH)
    ][:top_n]

    if not candidates:
        candidates = rows[: min(top_n, len(rows))]

    from ai.analyst import call_ai_scan

    prompt = _build_batch_prompt(candidates)
    text, provider = call_ai_scan(prompt, system=_SCAN_SYSTEM)
    if not text:
        return 0, "rule-based"

    notes = _parse_batch_response(text)
    updated = 0
    for row in rows:
        note = notes.get(row.ticker.upper())
        if note:
            row.ai_note = note
            row.ai_powered = True
            row.ai_provider = provider
            updated += 1

    return updated, provider

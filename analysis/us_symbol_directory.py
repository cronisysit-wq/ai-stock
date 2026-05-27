"""
US Symbol Directory — full NASDAQ/NYSE/AMEX listings (Robinhood-scale universe).

Source: NASDAQ Trader Symbol Directory (official US exchange listings)
  - nasdaqlisted.txt  (~5,000+ NASDAQ)
  - otherlisted.txt   (~4,000+ NYSE, AMEX, ARCA, etc.)

Cached locally for 24h to avoid repeated downloads.

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import logging
import re
import ssl
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_CACHE_DIR = Path(__file__).resolve().parent / "data"
_CACHE_FILE = _CACHE_DIR / "us_symbols_cache.txt"
_CACHE_META = _CACHE_DIR / "us_symbols_cache.meta"
_CACHE_TTL_SEC = 86400  # 24 hours

# Valid US ticker pattern (Yahoo Finance compatible: BRK-B, not BRK.B in directory)
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ai-trading-assistant/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_nasdaq_listed(text: str, include_etfs: bool = True) -> List[str]:
    symbols: List[str] = []
    for line in text.splitlines():
        if not line or line.startswith("File Creation") or line.startswith("Symbol|"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym = parts[0].strip().upper()
        test_issue = parts[3].strip().upper()
        is_etf = parts[6].strip().upper() == "Y"
        if test_issue == "Y" or not sym:
            continue
        if is_etf and not include_etfs:
            continue
        if _SYMBOL_RE.match(sym):
            symbols.append(sym)
    return symbols


def _parse_other_listed(text: str, include_etfs: bool = True) -> List[str]:
    symbols: List[str] = []
    for line in text.splitlines():
        if not line or line.startswith("File Creation") or line.startswith("ACT Symbol|"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        sym = parts[0].strip().upper()
        test_issue = parts[6].strip().upper()
        is_etf = parts[4].strip().upper() == "Y"
        if test_issue == "Y" or not sym:
            continue
        if is_etf and not include_etfs:
            continue
        if _SYMBOL_RE.match(sym):
            symbols.append(sym)
    return symbols


def _read_cache() -> Optional[List[str]]:
    try:
        if not _CACHE_FILE.exists() or not _CACHE_META.exists():
            return None
        age = time.time() - _CACHE_META.stat().st_mtime
        if age > _CACHE_TTL_SEC:
            return None
        lines = _CACHE_FILE.read_text(encoding="utf-8").splitlines()
        return [ln.strip().upper() for ln in lines if ln.strip()]
    except Exception as exc:
        logger.debug("Cache read failed: %s", exc)
        return None


def _write_cache(symbols: List[str]) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text("\n".join(symbols), encoding="utf-8")
        _CACHE_META.write_text(str(len(symbols)), encoding="utf-8")
    except Exception as exc:
        logger.debug("Cache write failed: %s", exc)


def fetch_all_us_symbols(
    include_etfs: bool = True,
    use_cache: bool = True,
) -> List[str]:
    """
    Fetch all US exchange-listed symbols (~8,000–11,000 with ETFs).

    Robinhood offers thousands of US stocks and ETFs — this matches that scale.
    """
    if use_cache and include_etfs:
        cached = _read_cache()
        if cached:
            return cached

    symbols: List[str] = []
    try:
        nasdaq_text = _fetch_url(NASDAQ_LISTED_URL)
        symbols.extend(_parse_nasdaq_listed(nasdaq_text, include_etfs=include_etfs))
    except Exception as exc:
        logger.warning("NASDAQ listed fetch failed: %s", exc)

    try:
        other_text = _fetch_url(OTHER_LISTED_URL)
        symbols.extend(_parse_other_listed(other_text, include_etfs=include_etfs))
    except Exception as exc:
        logger.warning("Other listed fetch failed: %s", exc)

    if not symbols:
        return _fallback_symbols()

    seen: set = set()
    deduped: List[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    if use_cache and deduped:
        _write_cache(deduped)

    return deduped


def _fallback_symbols() -> List[str]:
    """Offline fallback — curated lists only."""
    from analysis.universe import SP500, NASDAQ100_EXTRA, DAY_TRADING, ROBINHOOD_POPULAR

    combined = SP500 + NASDAQ100_EXTRA + ROBINHOOD_POPULAR + DAY_TRADING
    seen: set = set()
    out: List[str] = []
    for t in combined:
        tu = t.upper().replace(".", "-")
        if tu not in seen:
            seen.add(tu)
            out.append(tu)
    return out


def get_symbol_count(include_etfs: bool = True) -> int:
    return len(fetch_all_us_symbols(include_etfs=include_etfs, use_cache=True))


def refresh_symbol_cache() -> Tuple[int, str]:
    """Force refresh from NASDAQ Trader. Returns (count, status message)."""
    syms = fetch_all_us_symbols(include_etfs=True, use_cache=False)
    return len(syms), f"Refreshed {len(syms):,} US symbols from NASDAQ Trader directory."

"""
Instant scan loads from DB cache + background refresh every 5 minutes.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, Tuple

from analysis.scan_cache import load_scan_cache, save_scan_cache
from ui.auto_scan import get_auto_refresh_seconds, get_ui_poll_seconds

logger = logging.getLogger(__name__)

CACHE_VERSION = 1

_refresh_lock = threading.Lock()
_refresh_in_progress: set[str] = set()

# Lightweight UI poll — picks up background refresh without blocking
UI_POLL_SECONDS = 30


def strategy_cache_key(
    preset: str,
    limit: Optional[int],
    scan_all: bool,
    enable_ai_notes: bool,
) -> str:
    lim = "all" if scan_all else str(limit or 250)
    ai = "1" if enable_ai_notes else "0"
    return f"scan_v{CACHE_VERSION}:strategy:{preset}:{lim}:ai{ai}"


def us_cache_key(preset: str, limit: int, top_n: int) -> str:
    return f"scan_v{CACHE_VERSION}:us:{preset}:{limit}:top{top_n}"


def _is_stale(last_ts: Optional[float]) -> bool:
    if not last_ts:
        return True
    return (time.time() - last_ts) >= get_auto_refresh_seconds()


def _start_background(cache_key: str, runner: Callable[[], Any]) -> bool:
    """Start a daemon refresh if not already running. Returns True if started."""
    with _refresh_lock:
        if cache_key in _refresh_in_progress:
            return False
        _refresh_in_progress.add(cache_key)

    def _worker():
        try:
            logger.info("Background scan started: %s", cache_key)
            session = runner()
            if session is not None:
                save_scan_cache(cache_key, session)
                logger.info("Background scan saved: %s", cache_key)
        except Exception as exc:
            logger.warning("Background scan failed %s: %s", cache_key, exc)
        finally:
            with _refresh_lock:
                _refresh_in_progress.discard(cache_key)

    threading.Thread(target=_worker, daemon=True, name=f"scan-{cache_key[:48]}").start()
    return True


def is_refresh_running(cache_key: str) -> bool:
    with _refresh_lock:
        return cache_key in _refresh_in_progress


def resolve_strategy_scan(
    *,
    preset: str,
    limit: Optional[int],
    scan_all: bool,
    enable_ai_notes: bool,
    workers: int,
    force: bool,
    auto_refresh: bool,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[Any, Optional[float], str]:
    """
    Returns (session, last_ts, status).

    status: cached | refreshing | scanned | missing
    """
    cache_key = strategy_cache_key(preset, limit, scan_all, enable_ai_notes)
    cached, last_ts = load_scan_cache(cache_key)

    def _run():
        from analysis.strategy_sentiment_scanner import StrategySentimentScanner

        scanner = StrategySentimentScanner(max_workers=workers)
        actual_limit = None if scan_all else limit
        return scanner.scan(
            preset=preset,
            limit=actual_limit,
            progress_callback=progress_callback,
            enable_ai_notes=enable_ai_notes,
        )

    if force:
        session = _run()
        save_scan_cache(cache_key, session)
        return session, time.time(), "scanned"

    if cached is not None:
        if auto_refresh and _is_stale(last_ts):
            _start_background(cache_key, lambda: _run())
            return cached, last_ts, "refreshing"
        return cached, last_ts, "cached"

    if is_refresh_running(cache_key):
        return None, None, "waiting"

    session = _run()
    save_scan_cache(cache_key, session)
    return session, time.time(), "scanned"


def resolve_us_scan(
    *,
    preset: str,
    limit: int,
    top_n: int,
    workers: int,
    force: bool,
    auto_refresh: bool,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[Any, Optional[float], str]:
    cache_key = us_cache_key(preset, limit, top_n)
    cached, last_ts = load_scan_cache(cache_key)

    def _run():
        from analysis.us_market_sentiment import USMarketSentimentScanner

        scanner = USMarketSentimentScanner(max_workers=workers, top_n=top_n)
        return scanner.scan(preset=preset, progress_callback=progress_callback, limit=int(limit))

    if force:
        session = _run()
        save_scan_cache(cache_key, session)
        return session, time.time(), "scanned"

    if cached is not None:
        if auto_refresh and _is_stale(last_ts):
            _start_background(cache_key, lambda: _run())
            return cached, last_ts, "refreshing"
        return cached, last_ts, "cached"

    if is_refresh_running(cache_key):
        return None, None, "waiting"

    session = _run()
    save_scan_cache(cache_key, session)
    return session, time.time(), "scanned"


def warm_default_caches() -> None:
    """Kick off non-blocking background scans for default S&P presets."""
    from ui.auto_scan import DEFAULT_SCAN_LIMIT

    def _strategy_run():
        from analysis.strategy_sentiment_scanner import StrategySentimentScanner

        return StrategySentimentScanner(max_workers=10).scan(
            preset="sp500_full",
            limit=DEFAULT_SCAN_LIMIT,
            enable_ai_notes=True,
        )

    def _us_run():
        from analysis.us_market_sentiment import USMarketSentimentScanner

        return USMarketSentimentScanner(max_workers=10, top_n=50).scan(
            preset="sp500_full",
            limit=DEFAULT_SCAN_LIMIT,
        )

    jobs = [
        (strategy_cache_key("sp500_full", DEFAULT_SCAN_LIMIT, False, True), _strategy_run),
        (us_cache_key("sp500_full", DEFAULT_SCAN_LIMIT, 50), _us_run),
    ]
    for cache_key, runner in jobs:
        try:
            cached, last_ts = load_scan_cache(cache_key)
            if cached is not None and not _is_stale(last_ts):
                continue
            if is_refresh_running(cache_key):
                continue
            _start_background(cache_key, runner)
            logger.info("Warm cache queued: %s", cache_key)
        except Exception as exc:
            logger.debug("Warm cache skipped %s: %s", cache_key, exc)

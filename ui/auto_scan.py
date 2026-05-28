"""
Auto-scan helpers for Strategy Signals and US Market pages.

Runs an initial scan on page load, refreshes on a timer, and supports manual refresh.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import streamlit as st


def get_auto_refresh_seconds() -> int:
    try:
        from config.settings import get_settings
        return max(1, get_settings().SCAN_CACHE_REFRESH_MINUTES) * 60
    except Exception:
        return 5 * 60


def get_ui_poll_seconds() -> int:
    try:
        from config.settings import get_settings
        return max(10, get_settings().SCAN_UI_POLL_SECONDS)
    except Exception:
        return 30


AUTO_REFRESH_SECONDS = 5 * 60  # fallback; prefer get_auto_refresh_seconds()
UI_POLL_SECONDS = 30
DEFAULT_SCAN_LIMIT = 250


def scan_is_stale(last_scan_ts: Optional[float], *, interval: Optional[int] = None) -> bool:
    """True when no prior scan exists or the refresh interval has elapsed."""
    if interval is None:
        interval = get_auto_refresh_seconds()
    if not last_scan_ts:
        return True
    return (time.time() - last_scan_ts) >= interval


def format_scan_status(
    last_scan_ts: Optional[float],
    auto_refresh: bool,
    *,
    interval: Optional[int] = None,
    refreshing: bool = False,
) -> str:
    """Human-readable last-updated / next-refresh line for the UI."""
    if interval is None:
        interval = get_auto_refresh_seconds()
    if refreshing:
        return "🔄 Background refresh running — showing last saved results"

    if not last_scan_ts:
        return "No cached scan yet — first load may take 1–3 min"

    updated = datetime.fromtimestamp(last_scan_ts, tz=timezone.utc).strftime("%H:%M:%S UTC")
    elapsed = int(time.time() - last_scan_ts)
    mins, secs = divmod(elapsed, 60)

    if not auto_refresh:
        return f"Last updated {mins}m {secs}s ago ({updated}) · Auto-refresh off"

    remaining = max(0, interval - elapsed)
    rm, rs = divmod(remaining, 60)
    return (
        f"Last updated {mins}m {secs}s ago ({updated}) · "
        f"Next auto-refresh in {rm}m {rs}s"
    )


def trigger_autorefresh(interval_seconds: int, key: str) -> int:
    """
    Schedule periodic Streamlit reruns. Returns refresh counter (0 on first load).
    """
    try:
        from streamlit_autorefresh import st_autorefresh

        return st_autorefresh(interval=interval_seconds * 1000, key=key)
    except ImportError:
        return 0


def should_run_scan(
    *,
    session_key: str,
    last_ts_key: str,
    force: bool,
    auto_refresh: bool,
    interval: int = AUTO_REFRESH_SECONDS,
) -> bool:
    """Decide whether to launch a full universe scan on this run."""
    if force:
        return True
    if st.session_state.get(session_key) is None:
        return True
    if auto_refresh and scan_is_stale(st.session_state.get(last_ts_key), interval=interval):
        return True
    return False

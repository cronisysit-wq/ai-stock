"""
Persist scan results (Strategy Signals + US Market) for instant page loads.

Uses AppSettings (PostgreSQL on Railway, SQLite locally) as JSON blob storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_VERSION = 1


def _dt_to_str(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _str_to_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def strategy_session_to_dict(session) -> dict:
    from analysis.strategy_sentiment_scanner import StrategySentimentSession

    if not isinstance(session, StrategySentimentSession):
        raise TypeError("Expected StrategySentimentSession")
    data = asdict(session)
    data["scanned_at"] = _dt_to_str(session.scanned_at)
    data["scan_type"] = "strategy_sentiment"
    data["cache_version"] = CACHE_VERSION
    return data


def strategy_session_from_dict(data: dict):
    from analysis.strategy_sentiment_scanner import (
        StrategySentimentRow,
        StrategySentimentSession,
    )

    rows = [StrategySentimentRow(**r) for r in data.get("results", [])]
    scanned_at = _str_to_dt(data.get("scanned_at", ""))
    return StrategySentimentSession(
        session_id=data.get("session_id", ""),
        preset=data.get("preset", ""),
        universe_size=int(data.get("universe_size", 0)),
        scanned=int(data.get("scanned", 0)),
        results=rows,
        elapsed_seconds=float(data.get("elapsed_seconds", 0)),
        ai_scan_provider=data.get("ai_scan_provider", ""),
        scanned_at=scanned_at,
        disclaimer=data.get("disclaimer", StrategySentimentSession.disclaimer),
    )


def us_session_to_dict(session) -> dict:
    from analysis.us_market_sentiment import (
        SectorBreadth,
        USMarketSentimentSession,
        USSentimentRow,
    )

    if not isinstance(session, USMarketSentimentSession):
        raise TypeError("Expected USMarketSentimentSession")

    rows = []
    for r in session.results:
        d = asdict(r)
        d.pop("raw", None)
        rows.append(d)

    momentum = []
    for r in session.top_momentum:
        d = asdict(r)
        d.pop("raw", None)
        momentum.append(d)

    return {
        "cache_version": CACHE_VERSION,
        "scan_type": "us_market",
        "session_id": session.session_id,
        "preset": session.preset,
        "universe_size": session.universe_size,
        "scanned": session.scanned,
        "results": rows,
        "sector_breadth": [asdict(s) for s in session.sector_breadth],
        "market_bullish_pct": session.market_bullish_pct,
        "market_bearish_pct": session.market_bearish_pct,
        "market_neutral_pct": session.market_neutral_pct,
        "avg_sentiment": session.avg_sentiment,
        "top_momentum": momentum,
        "elapsed_seconds": session.elapsed_seconds,
        "scanned_at": _dt_to_str(session.scanned_at),
        "disclaimer": session.disclaimer,
    }


def us_session_from_dict(data: dict):
    from analysis.us_market_sentiment import (
        SectorBreadth,
        USMarketSentimentSession,
        USSentimentRow,
    )

    def _row(d: dict) -> USSentimentRow:
        d = dict(d)
        d.pop("raw", None)
        return USSentimentRow(**d)

    scanned_at = _str_to_dt(data.get("scanned_at", ""))
    return USMarketSentimentSession(
        session_id=data.get("session_id", ""),
        preset=data.get("preset", ""),
        universe_size=int(data.get("universe_size", 0)),
        scanned=int(data.get("scanned", 0)),
        results=[_row(r) for r in data.get("results", [])],
        sector_breadth=[SectorBreadth(**s) for s in data.get("sector_breadth", [])],
        market_bullish_pct=float(data.get("market_bullish_pct", 0)),
        market_bearish_pct=float(data.get("market_bearish_pct", 0)),
        market_neutral_pct=float(data.get("market_neutral_pct", 0)),
        avg_sentiment=float(data.get("avg_sentiment", 50)),
        top_momentum=[_row(r) for r in data.get("top_momentum", [])],
        elapsed_seconds=float(data.get("elapsed_seconds", 0)),
        scanned_at=scanned_at,
        disclaimer=data.get("disclaimer", USMarketSentimentSession.disclaimer),
    )


def load_scan_cache(cache_key: str):
    """Load cached scan session or None."""
    try:
        from db.database import init_db, get_db_session
        from db.models import AppSettings

        init_db()
        db = get_db_session()
        try:
            row = db.query(AppSettings).filter(AppSettings.key == cache_key).first()
            if not row or not row.value:
                return None, None
            envelope = json.loads(row.value)
            payload = envelope.get("payload", {})
            updated_at = float(envelope.get("updated_at_ts", 0))
            scan_type = payload.get("scan_type")
            if scan_type == "strategy_sentiment":
                return strategy_session_from_dict(payload), updated_at
            if scan_type == "us_market":
                return us_session_from_dict(payload), updated_at
            return None, None
        finally:
            db.close()
    except Exception as exc:
        logger.debug("load_scan_cache failed %s: %s", cache_key, exc)
        return None, None


def save_scan_cache(cache_key: str, session) -> None:
    """Persist scan session to AppSettings."""
    from analysis.strategy_sentiment_scanner import StrategySentimentSession
    from analysis.us_market_sentiment import USMarketSentimentSession

    if isinstance(session, StrategySentimentSession):
        payload = strategy_session_to_dict(session)
    elif isinstance(session, USMarketSentimentSession):
        payload = us_session_to_dict(session)
    else:
        raise TypeError(f"Unsupported session type: {type(session)}")

    envelope = {
        "updated_at_ts": datetime.now(timezone.utc).timestamp(),
        "payload": payload,
    }
    raw = json.dumps(envelope)

    try:
        from db.database import init_db, get_db_session
        from db.models import AppSettings

        init_db()
        db = get_db_session()
        try:
            row = db.query(AppSettings).filter(AppSettings.key == cache_key).first()
            now = datetime.utcnow()
            if row:
                row.value = raw
                row.updated_at = now
                row.description = "Auto scan cache"
            else:
                db.add(
                    AppSettings(
                        key=cache_key,
                        value=raw,
                        description="Auto scan cache",
                        updated_at=now,
                    )
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("save_scan_cache failed %s: %s", cache_key, exc)

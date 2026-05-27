"""
Robinhood Watchlist-Only Broker.

⚠️  IMPORTANT SAFETY NOTICE
============================
This module is WATCHLIST AND ANALYSIS ONLY.
It does NOT connect to Robinhood. It does NOT execute orders.
It does NOT store any Robinhood credentials.
It does NOT use any unofficial Robinhood API.
It does NOT scrape Robinhood.

Robinhood does not offer an official public stock trading API.
Order execution is NOT supported and will raise NotImplementedError.

Use this module only to:
- Manually record holdings and watchlist tickers for analysis.
- Import a CSV you manually exported from Robinhood.
- Display analysis of those tickers in the dashboard.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db.database import get_db_session
from db.models import Watchlist

logger = logging.getLogger(__name__)

# This constant is checked by the UI and executor to prevent order attempts
CAN_TRADE = False
BROKER_TYPE = "robinhood_watchlist"

_DISCLAIMER = (
    "\n\n⚠️ Robinhood mode is WATCHLIST/ANALYSIS ONLY. "
    "No orders can be placed. Robinhood does not provide an official "
    "public stock trading API. This assistant does not store Robinhood "
    "credentials or use unofficial APIs."
)


class RobinhoodWatchlistBroker:
    """
    Watchlist-only broker adapter for Robinhood holdings/watchlist analysis.

    This class mimics the broker interface so it can slot into the dashboard,
    but place_order() always raises NotImplementedError by design.
    """

    CAN_TRADE = False
    BROKER_TYPE = "robinhood_watchlist"

    def __init__(self) -> None:
        self._watchlist: List[str] = []
        self._holdings: Dict[str, float] = {}  # ticker → manually entered quantity
        self._kill_switch_engaged = False
        logger.info("RobinhoodWatchlistBroker initialized (watch-only, no trading)")

    # ── Watchlist management ────────────────────────────────────────────────

    def add_ticker(self, symbol: str) -> None:
        """Add a ticker to the watchlist."""
        symbol = symbol.strip().upper()
        if symbol and symbol not in self._watchlist:
            self._watchlist.append(symbol)
            self._save_to_db()

    def remove_ticker(self, symbol: str) -> None:
        """Remove a ticker from the watchlist."""
        symbol = symbol.strip().upper()
        if symbol in self._watchlist:
            self._watchlist.remove(symbol)
            self._save_to_db()

    def get_watchlist(self) -> List[str]:
        """Return the current watchlist tickers."""
        return list(self._watchlist)

    def set_holdings(self, holdings: Dict[str, float]) -> None:
        """Manually record holdings (ticker → quantity). Does not connect to Robinhood."""
        self._holdings = {k.upper(): float(v) for k, v in holdings.items()}

    def get_holdings(self) -> Dict[str, float]:
        """Return manually recorded holdings."""
        return dict(self._holdings)

    def import_from_csv(self, csv_content: str) -> List[str]:
        """
        Import tickers from a CSV string (user-exported from Robinhood).

        Looks for a 'Symbol' or 'Ticker' column. Returns list of imported tickers.
        Does NOT connect to Robinhood. User must paste/upload CSV manually.
        """
        imported = []
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            for row in reader:
                symbol = row.get("Symbol") or row.get("Ticker") or row.get("symbol") or row.get("ticker")
                if symbol:
                    symbol = symbol.strip().upper()
                    if symbol and symbol not in self._watchlist:
                        self._watchlist.append(symbol)
                        imported.append(symbol)
            self._save_to_db()
            logger.info("Imported %d tickers from CSV", len(imported))
        except Exception as exc:
            logger.error("CSV import failed: %s", exc)
        return imported

    # ── Broker interface (partial — analysis only) ───────────────────────────

    def get_account(self) -> Dict[str, Any]:
        """
        Returns a mock account dict.
        Robinhood data is NOT fetched — user must enter values manually.
        """
        return {
            "id": "robinhood_watchlist_only",
            "equity": 0.0,
            "buying_power": 0.0,
            "cash": 0.0,
            "portfolio_value": 0.0,
            "status": "watchlist_only",
            "currency": "USD",
            "note": "Robinhood watchlist mode — no real account data. Enter portfolio value manually.",
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return manually recorded holdings formatted as position dicts."""
        return [
            {
                "symbol": ticker,
                "qty": qty,
                "side": "long",
                "market_value": 0.0,   # not fetched — manual entry only
                "cost_basis": 0.0,
                "unrealized_pl": 0.0,
                "unrealized_plpc": 0.0,
                "current_price": 0.0,
                "avg_entry_price": 0.0,
                "change_today": 0.0,
                "note": "Manually entered holding",
            }
            for ticker, qty in self._holdings.items()
        ]

    def get_orders(self, **kwargs) -> List[Dict[str, Any]]:
        """No order history — orders are not supported."""
        return []

    def place_order(self, *args, **kwargs) -> None:
        """
        NOT SUPPORTED. Robinhood watchlist mode cannot place orders.

        Raises
        ------
        NotImplementedError
            Always. By design. This is not a bug.
        """
        raise NotImplementedError(
            "Robinhood Watchlist mode cannot place orders. "
            "Robinhood does not provide an official public stock trading API. "
            "Use Alpaca Paper or Alpaca Live for order execution." + _DISCLAIMER
        )

    def cancel_order(self, *args, **kwargs) -> None:
        raise NotImplementedError("Robinhood Watchlist mode does not support order cancellation.")

    def cancel_all_orders(self) -> None:
        raise NotImplementedError("Robinhood Watchlist mode does not support order cancellation.")

    @property
    def kill_switch_engaged(self) -> bool:
        return self._kill_switch_engaged

    def engage_kill_switch(self) -> None:
        self._kill_switch_engaged = True

    def disengage_kill_switch(self) -> None:
        self._kill_switch_engaged = False

    # ── DB persistence ──────────────────────────────────────────────────────

    def _save_to_db(self) -> None:
        """Persist watchlist tickers to the watchlists table."""
        try:
            db = get_db_session()
            existing = db.query(Watchlist).filter(Watchlist.name == "robinhood_manual").first()
            if existing:
                existing.tickers_json = json.dumps(self._watchlist)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                record = Watchlist(
                    name="robinhood_manual",
                    source="robinhood_manual",
                    tickers_json=json.dumps(self._watchlist),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(record)
            db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to save watchlist: %s", exc)

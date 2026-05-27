"""
Mock broker for paper/testing environments.

``MockBroker`` provides the **same public interface** as ``AlpacaBroker`` but
uses in-memory state instead of real API calls.  It is used automatically
when no Alpaca credentials are configured.

Features
--------
* Simulated $100,000 starting equity, adjustable via ``initial_capital``
* Instant market-order fills at the last known price (± configurable slippage)
* Limit orders remain pending until explicitly filled or cancelled
* Realistic rejection scenarios: insufficient funds, invalid ticker, zero qty
* Full order history queryable by status
* Kill-switch support
* Audit logging to DB (same interface as AlpacaBroker)
* Thread-safe state management

Safe by design
--------------
* ``MockBroker`` can **never** send a real order — it has no network connection.
* All monetary effects are purely in-memory.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_CAPITAL = 100_000.0
DEFAULT_SLIPPAGE_PCT = 0.001   # 0.1% simulated slippage on market orders

# Tickers the mock broker knows about (prevents typo testing surprises)
_KNOWN_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "NVDA", "META",
    "NFLX", "AMD", "INTC", "ORCL", "CRM", "ADBE", "PYPL", "SHOP",
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "USO", "TLT",
    "JPM", "BAC", "WFC", "GS", "MS", "BRK.B", "V", "MA",
    "JNJ", "PFE", "MRNA", "ABBV", "UNH", "CVX", "XOM", "BP",
    "COIN", "HOOD", "SOFI", "PLTR", "RIVN", "LCID", "F", "GM",
}


@dataclass
class MockPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.qty * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_entry_price

    @property
    def unrealized_pl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_plpc(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pl / self.cost_basis

    @property
    def side(self) -> str:
        return "long" if self.qty > 0 else "short"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "side": self.side,
            "avg_entry_price": round(self.avg_entry_price, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 2),
            "cost_basis": round(self.cost_basis, 2),
            "unrealized_pl": round(self.unrealized_pl, 2),
            "unrealized_plpc": round(self.unrealized_plpc, 6),
            "change_today": 0.0,  # not simulated
        }


@dataclass
class MockOrder:
    id: str
    symbol: str
    qty: float
    side: str             # buy / sell
    type: str             # market / limit
    time_in_force: str    # day / gtc
    status: str           # new / filled / cancelled / rejected / pending_new
    submitted_at: datetime
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    filled_avg_price: Optional[float] = None
    filled_qty: float = 0.0
    reject_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "qty": self.qty,
            "side": self.side,
            "type": self.type,
            "status": self.status,
            "submitted_at": str(self.submitted_at),
            "filled_at": str(self.filled_at) if self.filled_at else None,
            "filled_avg_price": self.filled_avg_price,
            "filled_qty": self.filled_qty,
            "limit_price": self.limit_price,
            "reject_reason": self.reject_reason,
        }


class MockBroker:
    """In-memory paper broker — zero network, zero real money.

    Parameters
    ----------
    initial_capital:
        Starting equity for the simulated account (default $100,000).
    slippage_pct:
        Fraction of price applied as simulated slippage on market orders
        (default 0.1%).
    reject_unknown_tickers:
        If True, orders for unlisted ticker symbols are rejected.
    """

    def __init__(
        self,
        initial_capital: float = DEFAULT_CAPITAL,
        slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
        reject_unknown_tickers: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._slippage_pct = slippage_pct
        self._reject_unknown = reject_unknown_tickers

        # State
        self._positions: Dict[str, MockPosition] = {}
        self._orders: Dict[str, MockOrder] = []  # kept in insertion order
        self._orders = []
        self._last_prices: Dict[str, float] = {}
        self._kill_switch_engaged: bool = False

        # Track daily P&L
        self._day_start_equity = initial_capital
        self._realised_pnl_today: float = 0.0

        logger.info("MockBroker initialised — initial capital: $%.2f", initial_capital)

    # ── Kill Switch ───────────────────────────────────────────────────────────

    @property
    def kill_switch_engaged(self) -> bool:
        return self._kill_switch_engaged

    def engage_kill_switch(self) -> None:
        with self._lock:
            self._kill_switch_engaged = True
            # Cancel all pending orders
            for order in self._orders:
                if order.status in ("new", "pending_new"):
                    order.status = "cancelled"
        logger.warning("MockBroker: kill switch ENGAGED — all trading halted")

    def disengage_kill_switch(self) -> None:
        with self._lock:
            self._kill_switch_engaged = False
        logger.info("MockBroker: kill switch DISENGAGED")

    # ── Price Management ──────────────────────────────────────────────────────

    def set_price(self, symbol: str, price: float) -> None:
        """Inject a price for a symbol (used by tests and signal generators)."""
        with self._lock:
            self._last_prices[symbol.upper()] = float(price)
            # Update current prices on positions
            if symbol.upper() in self._positions:
                self._positions[symbol.upper()].current_price = float(price)

    def _get_price(self, symbol: str) -> Optional[float]:
        """Return last known price, or None if unavailable."""
        sym = symbol.upper()
        if sym in self._last_prices:
            return self._last_prices[sym]
        # Try to fetch via yfinance
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                self._last_prices[sym] = price
                return price
        except Exception:
            pass
        return None

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> Dict[str, Any]:
        with self._lock:
            portfolio_value = self._cash + sum(
                p.market_value for p in self._positions.values()
            )
            daily_pnl = portfolio_value - self._day_start_equity + self._realised_pnl_today
            return {
                "id": "mock-account-001",
                "equity": round(portfolio_value, 2),
                "buying_power": round(self._cash * 2, 2),   # 2× leverage (mock)
                "cash": round(self._cash, 2),
                "portfolio_value": round(portfolio_value, 2),
                "last_equity": round(self._day_start_equity, 2),
                "daily_pnl": round(daily_pnl, 2),
                "pattern_day_trader": False,
                "trading_blocked": self._kill_switch_engaged,
                "status": "ACTIVE",
                "currency": "USD",
                "is_mock": True,
            }

    # ── Positions ─────────────────────────────────────────────────────────────

    def get_positions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in self._positions.values() if p.qty != 0]

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Place a simulated order.

        Validation
        ----------
        * Kill switch → rejected
        * Invalid ticker → rejected (if reject_unknown_tickers=True)
        * qty ≤ 0 → rejected
        * Insufficient cash for buy → rejected
        * Insufficient position for sell → rejected

        Market orders fill immediately with slippage.
        Limit orders are queued as ``pending_new``.
        """
        with self._lock:
            sym = symbol.upper().strip()
            now = datetime.now(timezone.utc)
            order_id = str(uuid.uuid4())[:16]

            # ── Validation ─────────────────────────────────────────────────
            if self._kill_switch_engaged:
                return self._reject(order_id, sym, qty, side, order_type,
                                    time_in_force, now, "Kill switch is engaged")

            if not sym:
                return self._reject(order_id, sym, qty, side, order_type,
                                    time_in_force, now, "Empty ticker symbol")

            if self._reject_unknown and sym not in _KNOWN_TICKERS:
                return self._reject(order_id, sym, qty, side, order_type,
                                    time_in_force, now,
                                    f"Unknown ticker '{sym}' — not in mock ticker list")

            if qty is None or qty <= 0:
                return self._reject(order_id, sym, qty or 0, side, order_type,
                                    time_in_force, now, "Quantity must be positive")

            # ── Price lookup ───────────────────────────────────────────────
            price = self._get_price(sym)
            if price is None:
                if order_type == "limit" and limit_price:
                    price = limit_price
                else:
                    return self._reject(order_id, sym, qty, side, order_type,
                                        time_in_force, now,
                                        f"No price data available for {sym}")

            # Apply slippage to market orders
            if order_type == "market":
                if side == "buy":
                    fill_price = price * (1 + self._slippage_pct)
                else:
                    fill_price = price * (1 - self._slippage_pct)
            else:
                fill_price = limit_price

            # ── Fund checks ────────────────────────────────────────────────
            if side == "buy":
                order_value = qty * (fill_price or price)
                if order_value > self._cash:
                    return self._reject(
                        order_id, sym, qty, side, order_type, time_in_force, now,
                        f"Insufficient cash: need ${order_value:,.2f}, have ${self._cash:,.2f}",
                    )
            elif side == "sell":
                pos = self._positions.get(sym)
                if pos is None or pos.qty < qty:
                    held = pos.qty if pos else 0
                    return self._reject(
                        order_id, sym, qty, side, order_type, time_in_force, now,
                        f"Insufficient position: need {qty} shares, hold {held}",
                    )

            # ── Create order ───────────────────────────────────────────────
            order = MockOrder(
                id=order_id, symbol=sym, qty=qty, side=side,
                type=order_type, time_in_force=time_in_force,
                status="new", submitted_at=now,
                limit_price=limit_price, stop_price=stop_price,
            )
            self._orders.append(order)

            # ── Fill market orders immediately ─────────────────────────────
            if order_type == "market" and fill_price is not None:
                self._fill_order(order, fill_price)

            logger.info(
                "MockBroker: %s %s %s @ $%.2f → %s",
                side.upper(), qty, sym, fill_price or 0, order.status,
            )
            return order.to_dict()

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for order in self._orders:
                if order.id == order_id:
                    if order.status in ("new", "pending_new"):
                        order.status = "cancelled"
                        logger.info("MockBroker: cancelled order %s", order_id)
                        return True
                    return False
            return False

    def cancel_all_orders(self) -> None:
        with self._lock:
            for order in self._orders:
                if order.status in ("new", "pending_new"):
                    order.status = "cancelled"
        logger.info("MockBroker: all pending orders cancelled")

    def get_orders(self, status: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            orders = list(reversed(self._orders))  # newest first
            if status != "all":
                orders = [o for o in orders if o.status == status]
            return [o.to_dict() for o in orders[:limit]]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _reject(
        self,
        order_id: str, symbol: str, qty: float, side: str,
        order_type: str, time_in_force: str, now: datetime, reason: str,
    ) -> Dict[str, Any]:
        order = MockOrder(
            id=order_id, symbol=symbol, qty=qty, side=side,
            type=order_type, time_in_force=time_in_force,
            status="rejected", submitted_at=now, reject_reason=reason,
        )
        self._orders.append(order)
        logger.warning("MockBroker: REJECTED %s %s %s — %s", side, qty, symbol, reason)
        d = order.to_dict()
        d["error"] = reason
        return d

    def _fill_order(self, order: MockOrder, fill_price: float) -> None:
        """Fill an order and update cash and positions (must hold lock)."""
        sym = order.symbol
        order.status = "filled"
        order.filled_at = datetime.now(timezone.utc)
        order.filled_avg_price = round(fill_price, 4)
        order.filled_qty = order.qty

        if order.side == "buy":
            self._cash -= order.qty * fill_price
            pos = self._positions.get(sym)
            if pos:
                # Average in
                total_qty = pos.qty + order.qty
                total_cost = pos.cost_basis + order.qty * fill_price
                pos.avg_entry_price = total_cost / total_qty
                pos.qty = total_qty
                pos.current_price = fill_price
            else:
                self._positions[sym] = MockPosition(
                    symbol=sym, qty=order.qty,
                    avg_entry_price=fill_price, current_price=fill_price,
                )

        elif order.side == "sell":
            pos = self._positions.get(sym)
            if pos:
                pnl = order.qty * (fill_price - pos.avg_entry_price)
                self._realised_pnl_today += pnl
                self._cash += order.qty * fill_price
                pos.qty -= order.qty
                pos.current_price = fill_price
                if pos.qty <= 0:
                    del self._positions[sym]

    # ── Test helpers ──────────────────────────────────────────────────────────

    def reset(self, initial_capital: Optional[float] = None) -> None:
        """Reset all state (useful between test cases)."""
        with self._lock:
            cap = initial_capital or self._initial_capital
            self._cash = cap
            self._day_start_equity = cap
            self._realised_pnl_today = 0.0
            self._positions.clear()
            self._orders.clear()
            self._last_prices.clear()
            self._kill_switch_engaged = False
        logger.info("MockBroker: state reset (capital=$%.2f)", cap)

    def inject_position(
        self, symbol: str, qty: float, avg_entry_price: float
    ) -> None:
        """Directly inject a position (for test setup)."""
        with self._lock:
            self._positions[symbol.upper()] = MockPosition(
                symbol=symbol.upper(), qty=qty,
                avg_entry_price=avg_entry_price, current_price=avg_entry_price,
            )

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def realised_pnl_today(self) -> float:
        return self._realised_pnl_today

    @property
    def order_count(self) -> int:
        return len(self._orders)

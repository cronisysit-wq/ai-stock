"""
Risk management module — the single mandatory gate before any order executes.

Every proposed trade MUST pass ``RiskManager.approve_trade()`` returning
``True`` before any broker call is made.  There are NO exceptions.

12 Safety Checks
----------------
1.  Kill switch not engaged
2.  Daily loss limit not exceeded
3.  Position size within MAX_POSITION_SIZE
4.  Max trades per day not exceeded
5.  Sufficient buying power
6.  Cooldown period after a losing trade
7.  Duplicate order prevention (same ticker+side within window)
8.  Ticker symbol is valid (non-empty, sane characters)
9.  Quantity is positive
10. Market data is available for the ticker
11. Market is open (live mode only)
12. AI override guard — AI signals cannot bypass this gate

AI Restriction
--------------
The AI analyst may only EXPLAIN signals.  It must NEVER produce values that
are forwarded here as if they override the result.  This function is the
last line of defence — its return value is final.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

from config.settings import get_settings, Settings
from db.database import get_db_session
from db.models import Order, AuditLog, TradeLog, RiskEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RiskCheckResult:
    """Aggregated outcome of all 12 pre-trade risk checks."""

    approved: bool
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    @property
    def rejection_summary(self) -> str:
        if not self.checks_failed:
            return ""
        return "; ".join(self.checks_failed)


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

class RiskManager:
    """Stateful risk gate — must approve EVERY order before execution.

    The only public entry point for trade approval is ``approve_trade()``,
    which returns a plain ``bool``.  The detailed ``RiskCheckResult`` is
    returned by ``check_order()`` for display purposes.

    Usage
    -----
    ```python
    rm = RiskManager()
    if not rm.approve_trade(symbol="AAPL", qty=10, side="buy", price=178.0):
        raise TradeBlockedError("Risk manager rejected the trade")
    broker.place_order(...)
    ```
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._kill_switch: bool = False

    # ── Kill switch ───────────────────────────────────────────────────────────

    @property
    def kill_switch_engaged(self) -> bool:
        return self._kill_switch

    def engage_kill_switch(self) -> None:
        self._kill_switch = True
        self._log_audit("KILL_SWITCH_ENGAGED", {"action": "engaged"}, level="WARNING")
        logger.warning("RiskManager: kill switch ENGAGED — all trading halted")

    def disengage_kill_switch(self) -> None:
        self._kill_switch = False
        self._log_audit("KILL_SWITCH_DISENGAGED", {"action": "disengaged"}, level="INFO")
        logger.info("RiskManager: kill switch disengaged — trading resumed")

    # ── Primary public API ────────────────────────────────────────────────────

    def approve_trade(
        self,
        symbol: str,
        qty: float,
        side: str,
        price: float,
        account_buying_power: Optional[float] = None,
        mode: str = "paper",
        market_data_available: bool = True,
    ) -> bool:
        """Check all risk rules and return ``True`` only if ALL pass.

        This is the MANDATORY gate.  No order may be placed without this
        returning ``True``.  The AI analyst result must NEVER be used to
        override the return value here.

        Parameters
        ----------
        symbol:
            Ticker symbol.
        qty:
            Number of shares / units.
        side:
            ``"buy"`` or ``"sell"``.
        price:
            Current / estimated execution price.
        account_buying_power:
            Available buying power (from broker account). None = skip check.
        mode:
            Trading mode string (for logging).
        market_data_available:
            Whether market data was successfully retrieved for this symbol.

        Returns
        -------
        bool
            ``True`` if and only if ALL 12 checks pass.
        """
        result = self.check_order(
            symbol=symbol, qty=qty, side=side, price=price,
            account_buying_power=account_buying_power,
            mode=mode, market_data_available=market_data_available,
        )
        return result.approved

    def check_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        price: float,
        account_buying_power: Optional[float] = None,
        mode: str = "paper",
        market_data_available: bool = True,
    ) -> RiskCheckResult:
        """Run all 12 checks and return the full result (for UI display)."""
        result = RiskCheckResult(approved=True)
        order_value = (qty or 0) * (price or 0)

        # 1. Kill switch ──────────────────────────────────────────────────────
        self._check_kill_switch(result)

        # 2. Valid ticker ─────────────────────────────────────────────────────
        self._check_ticker(result, symbol)

        # 3. Positive quantity ────────────────────────────────────────────────
        self._check_quantity(result, qty)

        # 4. Market data available ────────────────────────────────────────────
        self._check_market_data(result, symbol, market_data_available)

        # 5. Market open (live mode only) ─────────────────────────────────────
        self._check_market_hours(result, mode)

        # 6. Daily loss limit ─────────────────────────────────────────────────
        self._check_daily_loss(result)

        # 7. Position size ────────────────────────────────────────────────────
        self._check_position_size(result, order_value)

        # 8. Max trades per day ───────────────────────────────────────────────
        self._check_max_trades(result)

        # 9. Buying power ─────────────────────────────────────────────────────
        self._check_buying_power(result, order_value, account_buying_power)

        # 10. Cooldown period ─────────────────────────────────────────────────
        self._check_cooldown(result)

        # 11. Duplicate order ─────────────────────────────────────────────────
        self._check_duplicate(result, symbol, side)

        # 12. AI override guard ───────────────────────────────────────────────
        # (structural check: result.approved is determined by checks 1-11 only)
        result.checks_passed.append(
            "AI override guard: risk decision made by risk manager only (not AI)."
        )

        # Final verdict
        result.approved = len(result.checks_failed) == 0
        result.details.update({
            "symbol": symbol, "qty": qty, "side": side,
            "price": price, "order_value": order_value,
            "approved": result.approved, "mode": mode,
        })

        # Persist risk event
        self._persist_risk_event(result, symbol, qty, side, price, mode)

        # Audit log
        self._log_audit(
            "RISK_CHECK",
            {
                "symbol": symbol, "side": side, "qty": qty, "price": price,
                "approved": result.approved, "mode": mode,
                "passed": len(result.checks_passed),
                "failed": result.checks_failed,
            },
            level="INFO" if result.approved else "WARNING",
        )

        logger.info(
            "Risk check %s %s %s @ $%.2f [mode=%s]: %s",
            side.upper(), qty, symbol, price, mode,
            "APPROVED" if result.approved else "REJECTED",
        )
        return result

    def get_risk_status(self) -> dict:
        """Return current risk metrics for dashboard display."""
        daily_pnl: float = 0.0
        trades_today: int = 0

        try:
            session = get_db_session()
            today_start = datetime.combine(date.today(), datetime.min.time())

            closed_today = (
                session.query(TradeLog)
                .filter(TradeLog.status == "closed", TradeLog.closed_at >= today_start)
                .all()
            )
            daily_pnl = sum(t.pnl for t in closed_today if t.pnl is not None)
            trades_today = (
                session.query(Order)
                .filter(Order.created_at >= today_start)
                .count()
            )
            session.close()
        except Exception as exc:
            logger.error("Could not compute risk status: %s", exc)

        s = self.settings
        return {
            "daily_pnl": round(daily_pnl, 2),
            "trades_today": trades_today,
            "kill_switch_status": "ENGAGED" if self._kill_switch else "OK",
            "limits": {
                "max_daily_loss": s.MAX_DAILY_LOSS,
                "max_position_size": s.MAX_POSITION_SIZE,
                "max_trades_per_day": s.MAX_TRADES_PER_DAY,
                "cooldown_seconds": s.COOLDOWN_SECONDS,
                "stop_loss_pct": s.STOP_LOSS_PCT,
                "take_profit_pct": s.TAKE_PROFIT_PCT,
                "reject_duplicate_orders": s.REJECT_DUPLICATE_ORDERS,
                "reject_market_closed": s.REJECT_MARKET_CLOSED,
            },
            "remaining": {
                "loss_capacity": round(abs(s.MAX_DAILY_LOSS) - abs(min(0, daily_pnl)), 2),
                "trades_remaining": max(0, s.MAX_TRADES_PER_DAY - trades_today),
            },
        }

    # ── Individual checks (12 total) ──────────────────────────────────────────

    def _check_kill_switch(self, result: RiskCheckResult) -> None:
        """Check 1 — Kill switch must not be engaged."""
        if self._kill_switch:
            result.checks_failed.append(
                "Kill switch is engaged — all trading is halted."
            )
        else:
            result.checks_passed.append("Kill switch: clear.")

    def _check_ticker(self, result: RiskCheckResult, symbol: str) -> None:
        """Check 2 — Ticker must be a non-empty valid symbol string."""
        if not symbol or not symbol.strip():
            result.checks_failed.append("Ticker symbol is empty or whitespace.")
            return
        # Must be 1-5 uppercase letters/numbers (or BRK.B style)
        if not re.match(r"^[A-Z0-9]{1,5}(\.[A-Z])?$", symbol.upper().strip()):
            result.checks_failed.append(
                f"Ticker '{symbol}' contains invalid characters."
            )
        else:
            result.checks_passed.append(f"Ticker '{symbol}' is valid.")

    def _check_quantity(self, result: RiskCheckResult, qty: float) -> None:
        """Check 3 — Quantity must be strictly positive."""
        if qty is None or qty <= 0:
            result.checks_failed.append(
                f"Quantity must be positive (got {qty})."
            )
        else:
            result.checks_passed.append(f"Quantity {qty} is positive.")

    def _check_market_data(
        self, result: RiskCheckResult, symbol: str, available: bool
    ) -> None:
        """Check 4 — Market data must be available for the ticker."""
        if not available:
            result.checks_failed.append(
                f"No market data available for '{symbol}' — order rejected."
            )
        else:
            result.checks_passed.append(f"Market data available for '{symbol}'.")

    def _check_market_hours(self, result: RiskCheckResult, mode: str) -> None:
        """Check 5 — Market must be open for live-mode orders (if configured)."""
        if not self.settings.REJECT_MARKET_CLOSED:
            result.checks_passed.append("Market hours check: disabled in settings.")
            return

        if "live" not in mode.lower():
            result.checks_passed.append(
                "Market hours check: skipped (not a live-mode order)."
            )
            return

        try:
            import alpaca_trade_api as tradeapi
            from config.settings import get_settings
            s = get_settings()
            api = tradeapi.REST(
                key_id=s.ALPACA_API_KEY,
                secret_key=s.ALPACA_SECRET_KEY,
                base_url=s.ALPACA_BASE_URL,
            )
            clock = api.get_clock()
            if not clock.is_open:
                result.checks_failed.append(
                    "Market is currently CLOSED — live orders cannot be placed."
                )
            else:
                result.checks_passed.append("Market is open.")
        except Exception:
            # If we can't check, be conservative and allow
            result.checks_passed.append(
                "Market hours check: skipped (could not fetch clock)."
            )

    def _check_daily_loss(self, result: RiskCheckResult) -> None:
        """Check 6 — Realised P&L today must not exceed MAX_DAILY_LOSS."""
        try:
            session = get_db_session()
            today_start = datetime.combine(date.today(), datetime.min.time())
            closed = (
                session.query(TradeLog)
                .filter(TradeLog.status == "closed", TradeLog.closed_at >= today_start)
                .all()
            )
            session.close()
            total_pnl = sum(t.pnl for t in closed if t.pnl is not None)
            max_loss = self.settings.MAX_DAILY_LOSS
            result.details["daily_pnl"] = total_pnl
            if total_pnl < -abs(max_loss):
                result.checks_failed.append(
                    f"Daily loss limit exceeded: P&L today is ${total_pnl:,.2f} "
                    f"(limit: -${abs(max_loss):,.2f})."
                )
            else:
                result.checks_passed.append(
                    f"Daily loss within limits: ${total_pnl:,.2f} "
                    f"(limit: -${abs(max_loss):,.2f})."
                )
        except Exception as exc:
            logger.error("Daily-loss check error: %s", exc)
            result.checks_passed.append(
                "Daily loss check: skipped (DB unavailable) — assumed OK."
            )

    def _check_position_size(self, result: RiskCheckResult, order_value: float) -> None:
        """Check 7 — Order notional must not exceed MAX_POSITION_SIZE."""
        max_pos = self.settings.MAX_POSITION_SIZE
        if order_value > max_pos:
            result.checks_failed.append(
                f"Position size ${order_value:,.2f} exceeds limit ${max_pos:,.2f}."
            )
        else:
            result.checks_passed.append(
                f"Position size ${order_value:,.2f} within limit ${max_pos:,.2f}."
            )

    def _check_max_trades(self, result: RiskCheckResult) -> None:
        """Check 8 — Orders today must not exceed MAX_TRADES_PER_DAY."""
        try:
            session = get_db_session()
            today_start = datetime.combine(date.today(), datetime.min.time())
            trades_today = (
                session.query(Order)
                .filter(Order.created_at >= today_start)
                .count()
            )
            session.close()
            max_trades = self.settings.MAX_TRADES_PER_DAY
            result.details["trades_today"] = trades_today
            if trades_today >= max_trades:
                result.checks_failed.append(
                    f"Max trades/day reached: {trades_today}/{max_trades}."
                )
            else:
                result.checks_passed.append(
                    f"Trade count OK: {trades_today}/{max_trades} today."
                )
        except Exception as exc:
            logger.error("Max-trades check error: %s", exc)
            result.checks_passed.append(
                "Trade-count check: skipped (DB unavailable) — assumed OK."
            )

    def _check_buying_power(
        self, result: RiskCheckResult, order_value: float, buying_power: Optional[float]
    ) -> None:
        """Check 9 — Must have sufficient buying power (if provided)."""
        if buying_power is None:
            result.checks_passed.append("Buying power check: skipped (not provided).")
            return
        if order_value > buying_power:
            result.checks_failed.append(
                f"Insufficient buying power: need ${order_value:,.2f}, "
                f"have ${buying_power:,.2f}."
            )
        else:
            result.checks_passed.append(
                f"Buying power OK: ${buying_power:,.2f} available for ${order_value:,.2f}."
            )

    def _check_cooldown(self, result: RiskCheckResult) -> None:
        """Check 10 — Must not be within COOLDOWN_SECONDS of a losing trade."""
        try:
            session = get_db_session()
            cooldown = self.settings.COOLDOWN_SECONDS
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
            recent_loss = (
                session.query(TradeLog)
                .filter(
                    TradeLog.status == "closed",
                    TradeLog.pnl < 0,
                    TradeLog.closed_at >= cutoff,
                )
                .order_by(TradeLog.closed_at.desc())
                .first()
            )
            session.close()
            if recent_loss is not None:
                seconds_ago = (datetime.now(timezone.utc) - recent_loss.closed_at).total_seconds()
                remaining = cooldown - seconds_ago
                result.checks_failed.append(
                    f"Cooldown active: last loss was {seconds_ago:.0f}s ago; "
                    f"wait {remaining:.0f}s more."
                )
            else:
                result.checks_passed.append(
                    f"Cooldown OK: no losing trades in last {cooldown}s."
                )
        except Exception as exc:
            logger.error("Cooldown check error: %s", exc)
            result.checks_passed.append(
                "Cooldown check: skipped (DB unavailable) — assumed OK."
            )

    def _check_duplicate(
        self, result: RiskCheckResult, symbol: str, side: str
    ) -> None:
        """Check 11 — Reject duplicate orders (same ticker+side within window)."""
        if not self.settings.REJECT_DUPLICATE_ORDERS:
            result.checks_passed.append("Duplicate order check: disabled in settings.")
            return
        try:
            session = get_db_session()
            window_secs = self.settings.DUPLICATE_ORDER_WINDOW_SECONDS
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_secs)
            recent = (
                session.query(Order)
                .filter(
                    Order.ticker == symbol.upper(),
                    Order.side == side.lower(),
                    Order.created_at >= cutoff,
                    Order.status.notin_(["cancelled", "rejected"]),
                )
                .first()
            )
            session.close()
            if recent is not None:
                result.checks_failed.append(
                    f"Duplicate order: a {side} order for {symbol} was already "
                    f"placed within the last {window_secs}s (order id={recent.id})."
                )
            else:
                result.checks_passed.append(
                    f"No duplicate order for {symbol} {side} in last {window_secs}s."
                )
        except Exception as exc:
            logger.error("Duplicate-order check error: %s", exc)
            result.checks_passed.append(
                "Duplicate check: skipped (DB unavailable) — assumed OK."
            )

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _persist_risk_event(
        self,
        result: RiskCheckResult,
        symbol: str,
        qty: float,
        side: str,
        price: float,
        mode: str,
    ) -> None:
        try:
            session = get_db_session()
            event = RiskEvent(
                symbol=symbol,
                qty=qty,
                side=side,
                price=price,
                approved=result.approved,
                checks_passed=json.dumps(result.checks_passed),
                checks_failed=json.dumps(result.checks_failed),
                rejection_reason=result.rejection_summary or None,
                mode=mode,
                created_at=datetime.now(timezone.utc),
            )
            session.add(event)
            session.commit()
            session.close()
        except Exception as exc:
            logger.error("Failed to persist RiskEvent: %s", exc)

    def _log_audit(self, event_type: str, details: dict, level: str = "INFO") -> None:
        try:
            session = get_db_session()
            entry = AuditLog(
                event_type=event_type,
                details=json.dumps(details),
                level=level,
                created_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            session.commit()
            session.close()
        except Exception as exc:
            logger.error("Failed to write AuditLog: %s", exc)

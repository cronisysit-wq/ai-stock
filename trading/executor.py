"""
Trade execution engine — 6 operating modes.

Mode Hierarchy
--------------
MANUAL            — signals displayed only; NO orders placed.
SEMI_AUTO         — signals queued; human presses Approve.
AUTO_PAPER        — auto-executes on paper/mock; needs ENABLE_AUTO_MODE=True.
LIVE_MANUAL       — displays live-market signals; no auto execution.
LIVE_SEMI_AUTO    — queues live signals for human approval.
LIVE_AUTO         — auto-executes on live market; needs BOTH
                    ENABLE_LIVE_TRADING=True AND ENABLE_AUTO_LIVE_TRADING=True.

Safety Contract
---------------
* Every execution path MUST call ``risk_manager.approve_trade()`` and
  receive ``True`` before any broker call.
* The AI analyst result is advisory only — it NEVER controls execution.
* LIVE_AUTO is rejected unless both live flags are set in .env.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from trading.risk_manager import RiskManager, RiskCheckResult
from trading.strategies import SignalResult, SignalType
from trading.market_data import get_latest_price
from db.database import get_db_session
from db.models import Signal, Order, AuditLog
from config.settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class TradingMode(Enum):
    MANUAL = "manual"
    SEMI_AUTO = "semi_auto"
    AUTO_PAPER = "auto_paper"
    LIVE_MANUAL = "live_manual"
    LIVE_SEMI_AUTO = "live_semi_auto"
    LIVE_AUTO = "live_auto"   # requires ENABLE_LIVE_TRADING + ENABLE_AUTO_LIVE_TRADING
    APPROVAL_REQUIRED = "approval_required"  # live orders require user approval each time


# Human-readable labels used by the UI
TRADING_MODE_LABELS: Dict[TradingMode, str] = {
    TradingMode.MANUAL:             "Manual (paper)",
    TradingMode.SEMI_AUTO:          "Semi-Auto (paper)",
    TradingMode.AUTO_PAPER:         "Auto Paper",
    TradingMode.LIVE_MANUAL:        "Live — Manual",
    TradingMode.LIVE_SEMI_AUTO:     "Live — Semi-Auto",
    TradingMode.LIVE_AUTO:          "Live — Auto (⚠️ LOCKED)",
    TradingMode.APPROVAL_REQUIRED:  "Live — Approval Required",
}

LIVE_MODES = {TradingMode.LIVE_MANUAL, TradingMode.LIVE_SEMI_AUTO, TradingMode.LIVE_AUTO, TradingMode.APPROVAL_REQUIRED}


@dataclass
class ExecutionResult:
    """Outcome of a single execution attempt."""

    success: bool
    action_taken: str              # signal_displayed | queued | order_placed | blocked
    signal: SignalResult
    risk_check: Optional[RiskCheckResult] = None
    order_result: Optional[dict] = None
    message: str = ""
    mode: str = ""


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class TradeExecutor:
    """Orchestrates the full signal → approval → order lifecycle.

    Parameters
    ----------
    broker:
        AlpacaBroker or MockBroker instance.
    risk_manager:
        RiskManager instance (must be the same one shown in the UI).
    """

    def __init__(self, broker, risk_manager: Optional[RiskManager] = None) -> None:
        self.settings = get_settings()
        self.broker = broker
        self.risk_manager = risk_manager or RiskManager()
        self._pending_approvals: Dict[int, dict] = {}

    # ── Primary entry point ───────────────────────────────────────────────────

    def execute_signal(
        self,
        signal: SignalResult,
        ticker: str,
        qty: float,
        mode: TradingMode,
    ) -> ExecutionResult:
        """Process a strategy signal according to the current mode.

        Parameters
        ----------
        signal:
            Output from a strategy's ``generate_signal()``.
        ticker:
            Symbol to trade.
        qty:
            Requested number of shares.
        mode:
            One of the 6 ``TradingMode`` values.

        Returns
        -------
        ExecutionResult
        """
        signal_id = self._log_signal(signal, ticker)
        mode_str = mode.value

        self._log_audit(
            "SIGNAL_RECEIVED",
            {
                "signal_id": signal_id, "ticker": ticker,
                "signal": signal.signal.value, "strategy": signal.strategy,
                "confidence": signal.confidence, "mode": mode_str,
            },
        )

        # HOLD — nothing to execute in any mode
        if signal.signal == SignalType.HOLD:
            return ExecutionResult(
                success=True, action_taken="signal_displayed",
                signal=signal, mode=mode_str,
                message=f"HOLD signal for {ticker} — no action taken.",
            )

        side = "buy" if signal.signal == SignalType.BUY else "sell"

        # ── Guard: live mode requires ENABLE_LIVE_TRADING ─────────────────────
        if mode in LIVE_MODES and not self.settings.ENABLE_LIVE_TRADING:
            msg = (
                f"Live-mode order for {ticker} BLOCKED: "
                "ENABLE_LIVE_TRADING is not set to true."
            )
            self._log_audit("ORDER_BLOCKED_CONFIG", {"reason": msg, "mode": mode_str},
                            level="WARNING")
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=signal, mode=mode_str, message=msg,
            )

        # ── Guard: LIVE_AUTO requires BOTH flags ───────────────────────────────
        if mode == TradingMode.LIVE_AUTO and not self.settings.is_live_auto_trading_allowed:
            msg = (
                f"LIVE_AUTO order for {ticker} BLOCKED: "
                "Requires both ENABLE_LIVE_TRADING=true AND "
                "ENABLE_AUTO_LIVE_TRADING=true."
            )
            self._log_audit("ORDER_BLOCKED_CONFIG", {"reason": msg, "mode": mode_str},
                            level="WARNING")
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=signal, mode=mode_str, message=msg,
            )

        # ── Guard: AUTO_PAPER requires ENABLE_AUTO_MODE ────────────────────────
        if mode == TradingMode.AUTO_PAPER and not self.settings.ENABLE_AUTO_MODE:
            msg = (
                f"AUTO_PAPER order for {ticker} BLOCKED: "
                "ENABLE_AUTO_MODE is not set to true."
            )
            self._log_audit("ORDER_BLOCKED_CONFIG", {"reason": msg, "mode": mode_str},
                            level="WARNING")
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=signal, mode=mode_str, message=msg,
            )

        # ── Route by mode ──────────────────────────────────────────────────────
        if mode in (TradingMode.MANUAL, TradingMode.LIVE_MANUAL):
            return self._handle_display_only(signal, signal_id, ticker, mode_str)

        if mode in (TradingMode.SEMI_AUTO, TradingMode.LIVE_SEMI_AUTO):
            return self._handle_queue(signal, signal_id, ticker, qty, side, mode_str)

        # AUTO_PAPER or LIVE_AUTO
        return self._handle_auto(signal, signal_id, ticker, qty, side, mode_str)

    def approve_pending(self, signal_id: int, qty: float) -> ExecutionResult:
        """Human approves a queued (semi-auto) signal and executes it."""
        if signal_id not in self._pending_approvals:
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=SignalResult(
                    signal=SignalType.HOLD, confidence=0.0, strategy="unknown",
                    explanation="Signal not in pending queue.", indicators={},
                ),
                message=f"Signal ID {signal_id} not found in approval queue.",
            )

        pending = self._pending_approvals.pop(signal_id)
        signal: SignalResult = pending["signal"]
        ticker: str = pending["ticker"]
        side = "buy" if signal.signal == SignalType.BUY else "sell"
        mode_str = pending.get("mode", "semi_auto")

        self._log_audit(
            "SIGNAL_APPROVED",
            {"signal_id": signal_id, "ticker": ticker, "qty": qty, "mode": mode_str},
        )

        price = self._get_price(ticker)
        buying_power = self._get_buying_power()

        # MANDATORY: risk gate must approve
        approved = self.risk_manager.approve_trade(
            symbol=ticker, qty=qty, side=side, price=price,
            account_buying_power=buying_power, mode=mode_str,
            market_data_available=(price > 0),
        )
        risk_result = self.risk_manager.check_order(
            symbol=ticker, qty=qty, side=side, price=price,
            account_buying_power=buying_power, mode=mode_str,
            market_data_available=(price > 0),
        )

        if not approved:
            self._log_audit(
                "ORDER_BLOCKED_RISK",
                {"signal_id": signal_id, "ticker": ticker,
                 "failed": risk_result.checks_failed, "mode": mode_str},
                level="WARNING",
            )
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=signal, risk_check=risk_result, mode=mode_str,
                message=(
                    f"Approved signal for {ticker} blocked by risk: "
                    + risk_result.rejection_summary
                ),
            )

        order = self._place_order(ticker, qty, side, signal, signal_id, mode_str)
        return ExecutionResult(
            success=True, action_taken="order_placed",
            signal=signal, risk_check=risk_result, order_result=order,
            mode=mode_str,
            message=f"Order placed: {side.upper()} {qty} {ticker}.",
        )

    @property
    def pending_signals(self) -> Dict[int, dict]:
        return dict(self._pending_approvals)

    # ── Mode handlers ─────────────────────────────────────────────────────────

    def _handle_display_only(
        self, signal: SignalResult, signal_id: int, ticker: str, mode: str
    ) -> ExecutionResult:
        """Manual / Live-Manual: display signal only, never order."""
        self._log_audit(
            "SIGNAL_DISPLAYED",
            {"signal_id": signal_id, "ticker": ticker, "mode": mode},
        )
        return ExecutionResult(
            success=True, action_taken="signal_displayed",
            signal=signal, mode=mode,
            message=(
                f"{signal.signal.value} signal for {ticker} displayed "
                f"({mode} mode — no order placed)."
            ),
        )

    def _handle_queue(
        self,
        signal: SignalResult, signal_id: int, ticker: str,
        qty: float, side: str, mode: str,
    ) -> ExecutionResult:
        """Semi-Auto / Live-Semi-Auto: queue for human approval."""
        self._pending_approvals[signal_id] = {
            "signal": signal, "ticker": ticker, "qty": qty,
            "side": side, "queued_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
        }
        self._log_audit(
            "SIGNAL_QUEUED",
            {"signal_id": signal_id, "ticker": ticker, "mode": mode},
        )
        return ExecutionResult(
            success=True, action_taken="queued",
            signal=signal, mode=mode,
            message=(
                f"{signal.signal.value} for {ticker} queued for approval "
                f"(id={signal_id}). Use approve_pending() to execute."
            ),
        )

    def _handle_auto(
        self,
        signal: SignalResult, signal_id: int, ticker: str,
        qty: float, side: str, mode: str,
    ) -> ExecutionResult:
        """Auto modes: risk-check → place order if approved."""
        price = self._get_price(ticker)
        buying_power = self._get_buying_power()

        # MANDATORY GATE — no order without this returning True
        approved = self.risk_manager.approve_trade(
            symbol=ticker, qty=qty, side=side, price=price,
            account_buying_power=buying_power, mode=mode,
            market_data_available=(price > 0),
        )
        risk_result = self.risk_manager.check_order(
            symbol=ticker, qty=qty, side=side, price=price,
            account_buying_power=buying_power, mode=mode,
            market_data_available=(price > 0),
        )

        if not approved:
            self._log_audit(
                "ORDER_BLOCKED_RISK",
                {"signal_id": signal_id, "ticker": ticker,
                 "failed": risk_result.checks_failed, "mode": mode},
                level="WARNING",
            )
            return ExecutionResult(
                success=False, action_taken="blocked",
                signal=signal, risk_check=risk_result, mode=mode,
                message=(
                    f"Auto order for {ticker} blocked: "
                    + risk_result.rejection_summary
                ),
            )

        order = self._place_order(ticker, qty, side, signal, signal_id, mode)
        return ExecutionResult(
            success=True, action_taken="order_placed",
            signal=signal, risk_check=risk_result, order_result=order,
            mode=mode,
            message=f"Auto order placed: {side.upper()} {qty} {ticker}.",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _place_order(
        self,
        ticker: str, qty: float, side: str,
        signal: SignalResult, signal_id: int, mode: str,
    ) -> dict:
        """Submit the order through the broker and persist it."""
        try:
            order_result = self.broker.place_order(
                symbol=ticker, qty=qty, side=side,
                order_type="market", time_in_force="day",
            )
            try:
                session = get_db_session()
                db_order = Order(
                    ticker=ticker, side=side, qty=qty, order_type="market",
                    status=order_result.get("status", "submitted"),
                    broker_order_id=order_result.get("id", ""),
                    fill_price=order_result.get("filled_avg_price"),
                    signal_id=signal_id,
                    mode=mode,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(db_order)
                session.commit()
                session.close()
            except Exception as db_exc:
                logger.error("Failed to persist Order: %s", db_exc)

            self._log_audit(
                "ORDER_PLACED",
                {
                    "signal_id": signal_id, "ticker": ticker, "side": side,
                    "qty": qty, "mode": mode,
                    "broker_id": order_result.get("id"),
                    "status": order_result.get("status"),
                },
            )
            return order_result

        except Exception as exc:
            self._log_audit(
                "ORDER_ERROR",
                {"signal_id": signal_id, "ticker": ticker, "error": str(exc),
                 "mode": mode},
                level="ERROR",
            )
            logger.error("Order placement failed: %s", exc)
            return {"error": str(exc), "status": "error"}

    def _log_signal(self, signal: SignalResult, ticker: str) -> int:
        try:
            session = get_db_session()
            db_signal = Signal(
                ticker=ticker, strategy=signal.strategy,
                signal_type=signal.signal.value, confidence=signal.confidence,
                explanation=signal.explanation, created_at=datetime.now(timezone.utc),
            )
            session.add(db_signal)
            session.commit()
            session.refresh(db_signal)
            sid = db_signal.id
            session.close()
            return sid
        except Exception as exc:
            logger.error("Failed to persist Signal: %s", exc)
            return -1

    def _log_audit(
        self, event_type: str, details: dict, level: str = "INFO"
    ) -> None:
        try:
            session = get_db_session()
            session.add(AuditLog(
                event_type=event_type, details=json.dumps(details),
                level=level, created_at=datetime.now(timezone.utc),
            ))
            session.commit()
            session.close()
        except Exception as exc:
            logger.error("Failed to write AuditLog: %s", exc)

    def _get_price(self, ticker: str) -> float:
        try:
            return get_latest_price(ticker) or 0.0
        except Exception:
            return 0.0

    def _get_buying_power(self) -> Optional[float]:
        try:
            return float(self.broker.get_account().get("buying_power", 0))
        except Exception:
            return None

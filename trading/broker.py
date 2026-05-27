"""
Alpaca broker wrapper.

Provides a high-level interface for account info, positions, and order
management.  Every state-changing action is recorded in the AuditLog table.
A kill-switch mechanism can halt all trading instantly.
"""

import alpaca_trade_api as tradeapi
from config.settings import get_settings
from db.database import get_db_session
from db.models import AuditLog
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class LiveTradingDisabledError(Exception):
    """Raised when a live trading URL is used but ENABLE_LIVE_TRADING is False."""
    pass


class AlpacaBroker:
    """Wrapper around the Alpaca REST API with audit logging and kill-switch."""

    def __init__(self):
        self.settings = get_settings()
        self._validate_trading_mode()
        self.api = tradeapi.REST(
            key_id=self.settings.ALPACA_API_KEY,
            secret_key=self.settings.ALPACA_SECRET_KEY,
            base_url=self.settings.ALPACA_BASE_URL,
            api_version="v2",
        )
        self._kill_switch_engaged = False

    # ------------------------------------------------------------------
    # Safety & validation
    # ------------------------------------------------------------------

    def _validate_trading_mode(self):
        """Prevent accidental live trading when the flag is not set."""
        if not self.settings.is_paper_trading and not self.settings.ENABLE_LIVE_TRADING:
            raise LiveTradingDisabledError(
                "Live trading URL detected but ENABLE_LIVE_TRADING is not set to true. "
                "Set ENABLE_LIVE_TRADING=true in .env to enable live trading."
            )

    def _log_event(self, event_type: str, details: dict, level: str = "INFO"):
        """Persist an audit event to the database."""
        try:
            db = get_db_session()
            log = AuditLog(
                event_type=event_type,
                details=json.dumps(details),
                level=level,
                created_at=datetime.utcnow(),
            )
            db.add(log)
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Failed to log event: {e}")

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------

    @property
    def kill_switch_engaged(self) -> bool:
        """Whether the kill switch is currently active."""
        return self._kill_switch_engaged

    def engage_kill_switch(self):
        """Activate the kill switch – cancels all open orders immediately."""
        self._kill_switch_engaged = True
        self._log_event(
            "KILL_SWITCH_ENGAGED",
            {"message": "Emergency kill switch activated"},
            "WARNING",
        )
        try:
            self.api.cancel_all_orders()
            self._log_event(
                "ALL_ORDERS_CANCELLED",
                {"message": "All open orders cancelled via kill switch"},
                "WARNING",
            )
        except Exception as e:
            self._log_event("KILL_SWITCH_ERROR", {"error": str(e)}, "ERROR")

    def disengage_kill_switch(self):
        """Deactivate the kill switch, allowing trading to resume."""
        self._kill_switch_engaged = False
        self._log_event(
            "KILL_SWITCH_DISENGAGED",
            {"message": "Kill switch deactivated"},
            "INFO",
        )

    # ------------------------------------------------------------------
    # Account & positions
    # ------------------------------------------------------------------

    def get_account(self) -> Dict[str, Any]:
        """Return a dictionary with current account details."""
        try:
            account = self.api.get_account()
            return {
                "id": account.id,
                "equity": float(account.equity),
                "buying_power": float(account.buying_power),
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "status": account.status,
                "currency": account.currency,
                "last_equity": float(account.last_equity),
                "daily_pnl": float(account.equity) - float(account.last_equity),
            }
        except Exception as e:
            self._log_event("ACCOUNT_ERROR", {"error": str(e)}, "ERROR")
            raise

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return a list of current open positions."""
        try:
            positions = self.api.list_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "side": p.side,
                    "market_value": float(p.market_value),
                    "cost_basis": float(p.cost_basis),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc),
                    "current_price": float(p.current_price),
                    "avg_entry_price": float(p.avg_entry_price),
                    "change_today": float(p.change_today),
                }
                for p in positions
            ]
        except Exception as e:
            self._log_event("POSITIONS_ERROR", {"error": str(e)}, "ERROR")
            raise

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

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
        """Submit an order. Blocked when the kill switch is engaged."""
        if self._kill_switch_engaged:
            self._log_event(
                "ORDER_BLOCKED",
                {"reason": "Kill switch engaged", "symbol": symbol},
                "WARNING",
            )
            raise Exception("Kill switch is engaged. All trading is halted.")

        order_details = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "order_type": order_type,
            "time_in_force": time_in_force,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "mode": "paper" if self.settings.is_paper_trading else "live",
        }
        self._log_event("ORDER_SUBMITTED", order_details)

        try:
            kwargs: Dict[str, Any] = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "type": order_type,
                "time_in_force": time_in_force,
            }
            if limit_price:
                kwargs["limit_price"] = limit_price
            if stop_price:
                kwargs["stop_price"] = stop_price

            order = self.api.submit_order(**kwargs)
            result = {
                "id": order.id,
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side,
                "type": order.type,
                "status": order.status,
                "submitted_at": str(order.submitted_at),
                "filled_at": str(order.filled_at) if order.filled_at else None,
                "filled_avg_price": (
                    float(order.filled_avg_price)
                    if order.filled_avg_price
                    else None
                ),
            }
            self._log_event("ORDER_ACCEPTED", result)
            return result
        except Exception as e:
            self._log_event(
                "ORDER_ERROR", {**order_details, "error": str(e)}, "ERROR"
            )
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a single order by its broker ID."""
        try:
            self.api.cancel_order(order_id)
            self._log_event("ORDER_CANCELLED", {"order_id": order_id})
            return True
        except Exception as e:
            self._log_event(
                "CANCEL_ERROR", {"order_id": order_id, "error": str(e)}, "ERROR"
            )
            raise

    def get_orders(
        self, status: str = "all", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List orders filtered by status."""
        try:
            orders = self.api.list_orders(status=status, limit=limit)
            return [
                {
                    "id": o.id,
                    "symbol": o.symbol,
                    "qty": o.qty,
                    "side": o.side,
                    "type": o.type,
                    "status": o.status,
                    "submitted_at": str(o.submitted_at),
                    "filled_at": str(o.filled_at) if o.filled_at else None,
                    "filled_avg_price": (
                        float(o.filled_avg_price)
                        if o.filled_avg_price
                        else None
                    ),
                }
                for o in orders
            ]
        except Exception as e:
            self._log_event("ORDERS_ERROR", {"error": str(e)}, "ERROR")
            raise

    def cancel_all_orders(self):
        """Cancel every open order."""
        try:
            self.api.cancel_all_orders()
            self._log_event(
                "ALL_ORDERS_CANCELLED", {"message": "All open orders cancelled"}
            )
        except Exception as e:
            self._log_event("CANCEL_ALL_ERROR", {"error": str(e)}, "ERROR")
            raise

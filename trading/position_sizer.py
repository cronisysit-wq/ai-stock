"""
Position Sizer — risk-based trade size calculator.

Sizing is based on account size, max risk per trade, stop-loss distance,
max position size, and volatility. The most conservative limit wins.

Safety
------
* The app suggests quantity — the user can only reduce, never increase.
* Quantity is always capped at MAX_POSITION_SIZE / current_price.
* Quantity is always capped by risk-based sizing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SizingResult:
    """Result of a position sizing calculation."""
    suggested_qty: float
    max_allowed_qty: float
    risk_amount_usd: float
    stop_loss_price: float
    take_profit_price: float
    sizing_method: str
    capped_by: str           # 'max_position_size' | 'max_risk_per_trade' | 'volatility' | 'none'
    warning: str = ""


class PositionSizer:
    """
    Calculates a safe position size for a given trade.

    Parameters
    ----------
    settings:
        Optional Settings override (uses get_settings() by default).
    """

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()

    def calculate(
        self,
        current_price: float,
        account_equity: float,
        stop_loss_price: float,
        atr_pct: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> SizingResult:
        """
        Calculate recommended position size.

        Parameters
        ----------
        current_price:
            Current market price per share.
        account_equity:
            Total account equity in USD.
        stop_loss_price:
            Price at which stop-loss triggers.
        atr_pct:
            ATR as percentage of price (optional, used for volatility cap).
        take_profit_price:
            Target take-profit price (optional, for display).

        Returns
        -------
        SizingResult with suggested_qty and max_allowed_qty.
        The user may submit any quantity between 1 and max_allowed_qty.
        """
        if current_price <= 0:
            return self._error_result("Invalid price (must be > 0)")
        if account_equity <= 0:
            return self._error_result("Invalid account equity")
        if stop_loss_price <= 0 or stop_loss_price >= current_price:
            # Default stop-loss to settings percentage
            stop_loss_price = current_price * (1 - self.settings.STOP_LOSS_PCT / 100)

        stop_distance = current_price - stop_loss_price
        if stop_distance <= 0:
            stop_distance = current_price * 0.02  # fallback 2%

        # ── Method 1: Risk-based sizing ──────────────────────────────────────
        max_risk_usd = account_equity * (self.settings.MAX_RISK_PER_TRADE_PERCENT / 100)
        risk_based_qty = max_risk_usd / stop_distance

        # ── Method 2: Position-size cap ──────────────────────────────────────
        position_cap_qty = self.settings.MAX_POSITION_SIZE / current_price

        # ── Method 3: Volatility adjustment ──────────────────────────────────
        volatility_cap_qty = float("inf")
        volatility_warning = ""
        if atr_pct is not None and atr_pct > 3.0:
            volatility_cap_qty = risk_based_qty * 0.75  # reduce by 25% for high volatility
            volatility_warning = f"High volatility (ATR={atr_pct:.1f}%). Quantity reduced 25%."

        # ── Most conservative wins ────────────────────────────────────────────
        suggested = min(risk_based_qty, position_cap_qty, volatility_cap_qty)
        suggested = max(0.0, suggested)

        # Determine what capped it
        if suggested == position_cap_qty and position_cap_qty < risk_based_qty:
            capped_by = "max_position_size"
        elif suggested == volatility_cap_qty:
            capped_by = "volatility"
        elif risk_based_qty <= position_cap_qty:
            capped_by = "max_risk_per_trade"
        else:
            capped_by = "none"

        # Round down to whole shares (fractional shares not supported by default)
        suggested_qty = max(1.0, round(suggested, 0))
        max_allowed_qty = suggested_qty  # user cannot exceed this

        tp = take_profit_price or round(current_price * (1 + self.settings.TAKE_PROFIT_PCT / 100), 2)

        return SizingResult(
            suggested_qty=suggested_qty,
            max_allowed_qty=max_allowed_qty,
            risk_amount_usd=round(stop_distance * suggested_qty, 2),
            stop_loss_price=round(stop_loss_price, 2),
            take_profit_price=round(tp, 2),
            sizing_method="risk_per_trade",
            capped_by=capped_by,
            warning=volatility_warning,
        )

    def _error_result(self, reason: str) -> SizingResult:
        logger.warning("PositionSizer: %s", reason)
        return SizingResult(
            suggested_qty=0.0,
            max_allowed_qty=0.0,
            risk_amount_usd=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            sizing_method="error",
            capped_by="error",
            warning=reason,
        )

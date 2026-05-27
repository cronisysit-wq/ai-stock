"""
Day-trade position sizing — Wall-Street style R-multiple sizing.

Scales automatically with account equity:
  risk_budget = equity × risk_per_trade_pct
  shares      = risk_budget / stop_distance
  profit@2R   = shares × stop_distance × R:R

$100–$200 on a $10k account ≈ 1–2% daily target reference.
Same rules on $100k → $1k–$2k targets at the same percentages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class DayTradeSizingResult:
    """Professional day-trade sizing output."""
    shares: int
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    risk_usd: float
    reward_usd: float
    risk_reward_ratio: float
    notional_usd: float
    risk_pct_of_equity: float
    capped_by: str
    warning: str = ""


class DayTradeSizer:
    """
    ATR-aware intraday sizing with minimum 1:2 R:R default.

    Stop placement: max(0.5 × ATR, stop_loss_pct × price) below entry.
    Size: floor(risk_budget / stop_distance), capped by allocation & max position.
    """

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()

    def size(
        self,
        entry_price: float,
        account_equity: float,
        atr_pct: Optional[float] = None,
        atr_dollars: Optional[float] = None,
        stop_loss_pct: float = 1.0,
        risk_reward_ratio: float = 2.0,
        risk_per_trade_pct: Optional[float] = None,
        max_allocation_pct: Optional[float] = None,
    ) -> DayTradeSizingResult:
        if entry_price <= 0 or account_equity <= 0:
            return self._empty("Invalid price or equity")

        risk_pct = risk_per_trade_pct if risk_per_trade_pct is not None else min(
            self.settings.MAX_RISK_PER_TRADE_PERCENT, 1.0
        )
        alloc_pct = max_allocation_pct or self.settings.MAX_PORTFOLIO_ALLOCATION_PER_TICKER_PERCENT

        # ATR-based stop distance
        if atr_dollars and atr_dollars > 0:
            atr_stop = atr_dollars * 0.5
        elif atr_pct and atr_pct > 0:
            atr_stop = entry_price * atr_pct / 100 * 0.5
        else:
            atr_stop = entry_price * stop_loss_pct / 100

        pct_stop = entry_price * stop_loss_pct / 100
        stop_distance = max(atr_stop, pct_stop, entry_price * 0.003)  # min 0.3% stop

        stop_loss = round(entry_price - stop_distance, 2)
        take_profit = round(entry_price + stop_distance * risk_reward_ratio, 2)

        risk_budget = account_equity * risk_pct / 100
        raw_shares = int(risk_budget / stop_distance)

        # Caps
        alloc_cap = int(account_equity * alloc_pct / 100 / entry_price)
        position_cap = int(self.settings.MAX_POSITION_SIZE / entry_price)
        shares = max(0, min(raw_shares, alloc_cap, position_cap))

        capped_by = "none"
        if shares == 0:
            return self._empty("Position size rounds to zero — increase equity or widen stop")
        if shares == position_cap and position_cap < raw_shares:
            capped_by = "max_position_size"
        elif shares == alloc_cap and alloc_cap < raw_shares:
            capped_by = "max_allocation"
        else:
            capped_by = "risk_per_trade"

        warning = ""
        if atr_pct and atr_pct > 4.0:
            shares = max(1, int(shares * 0.75))
            warning = f"High volatility (ATR {atr_pct:.1f}%) — size reduced 25%."

        risk_usd = round(shares * stop_distance, 2)
        reward_usd = round(shares * stop_distance * risk_reward_ratio, 2)
        notional = round(shares * entry_price, 2)

        return DayTradeSizingResult(
            shares=shares,
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            stop_distance=round(stop_distance, 4),
            risk_usd=risk_usd,
            reward_usd=reward_usd,
            risk_reward_ratio=risk_reward_ratio,
            notional_usd=notional,
            risk_pct_of_equity=round(risk_usd / account_equity * 100, 3),
            capped_by=capped_by,
            warning=warning,
        )

    @staticmethod
    def _empty(reason: str) -> DayTradeSizingResult:
        return DayTradeSizingResult(
            shares=0, entry_price=0, stop_loss=0, take_profit=0,
            stop_distance=0, risk_usd=0, reward_usd=0,
            risk_reward_ratio=2.0, notional_usd=0, risk_pct_of_equity=0,
            capped_by="error", warning=reason,
        )

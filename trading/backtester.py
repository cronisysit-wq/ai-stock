"""
Walk-forward backtesting engine — upgraded with:

* Look-ahead bias prevention (signal generated on bar i uses only data[:i])
* Execution on NEXT bar open price (not same-bar close) to avoid look-ahead
* Commission/fee modelling (flat fee per trade)
* Slippage modelling (percentage of price)
* Expanded metrics: worst_day, consecutive_losing_trades, avg_holding_days,
  profit_factor, calmar_ratio, sortino_ratio
* Daily equity curve (one point per calendar day)

⚠️ DISCLAIMER: Backtests are SIMULATED results on historical data.
They do NOT guarantee future performance.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from trading.strategies import BaseStrategy, SignalType, get_strategy
from trading.market_data import get_historical_data, add_indicators

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    """Record of a single round-trip trade."""
    entry_date: str
    exit_date: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float           # net P&L after fees & slippage
    pnl_pct: float
    fee: float           # total fees paid on this trade
    slippage: float      # total slippage cost
    holding_days: int    # calendar days held


@dataclass
class BacktestResult:
    """Aggregate result of a backtest run."""
    # Core metrics
    total_return: float
    total_return_pct: float
    win_rate: float
    max_drawdown: float
    max_drawdown_pct: float
    num_trades: int
    winning_trades: int
    losing_trades: int
    avg_profit: float
    avg_loss: float
    avg_pnl: float
    sharpe_ratio: float
    # New metrics
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float          # gross wins / gross losses
    worst_day_pnl: float          # worst single-day portfolio change
    worst_day_date: str
    consecutive_losing_trades: int
    avg_holding_days: float
    total_fees: float
    total_slippage: float
    # Curve & trades
    equity_curve: List[float]
    dates: List[str]
    trades: List[BacktestTrade]
    initial_capital: float
    final_capital: float


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

class Backtester:
    """Walk-forward backtesting engine.

    Look-ahead bias prevention
    --------------------------
    At bar ``i``, the strategy only sees ``df.iloc[:i]`` (data up to but NOT
    including bar ``i``).  The signal is then executed at bar ``i``'s OPEN
    price, which is the earliest price we could realistically fill at.

    This ensures no future information leaks into the signal.
    """

    def run(
        self,
        symbol: str,
        start: str,
        end: str,
        strategy_name: str,
        initial_capital: float = 10_000.0,
        position_size_pct: float = 0.1,
        fee_per_trade: float = 1.00,       # USD per order
        slippage_pct: float = 0.001,       # 0.1% of price
    ) -> BacktestResult:
        """Execute a backtst.

        Parameters
        ----------
        symbol:
            Ticker symbol.
        start, end:
            ISO date strings (e.g. "2023-01-01").
        strategy_name:
            Name matching ``get_strategy()``.
        initial_capital:
            Starting cash.
        position_size_pct:
            Fraction of capital per trade (e.g. 0.10 = 10%).
        fee_per_trade:
            Flat commission per order in USD.
        slippage_pct:
            Price impact as a fraction (e.g. 0.001 = 0.1%).

        Returns
        -------
        BacktestResult

        ⚠️ Results are simulated and do NOT predict future performance.
        """
        logger.info(
            "Backtesting %s on %s [%s → %s] fee=$%.2f slip=%.2f%%",
            strategy_name, symbol, start, end, fee_per_trade, slippage_pct * 100,
        )

        # ── 1. Data acquisition ───────────────────────────────────────────────
        df = get_historical_data(symbol, start=start, end=end)
        if df is None or df.empty:
            logger.warning("No historical data for %s", symbol)
            return self._empty_result(initial_capital)

        df = add_indicators(df)
        if df is None or df.empty:
            return self._empty_result(initial_capital)

        strategy: BaseStrategy = get_strategy(strategy_name)

        # ── 2. Walk-forward simulation ────────────────────────────────────────
        cash = initial_capital
        position_qty: float = 0.0
        entry_price: float = 0.0
        entry_date: str = ""
        entry_index: int = 0

        trades: List[BacktestTrade] = []
        equity_curve: List[float] = []
        dates: List[str] = []

        min_window = 52   # need at least 52 bars of history

        for i in range(len(df)):
            row = df.iloc[i]
            bar_open = float(row.get("open", row["close"]))
            bar_close = float(row["close"])
            bar_date = str(df.index[i])[:10]

            # Portfolio value (mark-to-market at close)
            portfolio_value = cash + position_qty * bar_close
            equity_curve.append(round(portfolio_value, 2))
            dates.append(bar_date)

            # Need enough history — signal uses df[:i] (not including bar i)
            if i < min_window + 1:
                continue

            # ── Generate signal using ONLY past data (no look-ahead) ──────────
            past_window = df.iloc[:i]    # strictly before bar i
            try:
                sig = strategy.generate_signal(past_window)
            except Exception as exc:
                logger.debug("Strategy error at bar %d: %s", i, exc)
                continue

            # ── Execute at bar i OPEN price (± slippage) ──────────────────────
            if sig.signal == SignalType.BUY and position_qty == 0:
                fill_price = bar_open * (1 + slippage_pct)   # buy: pay more
                alloc = cash * position_size_pct
                qty = int(alloc / fill_price) if fill_price > 0 else 0
                if qty > 0:
                    cost = qty * fill_price + fee_per_trade
                    if cost <= cash:
                        cash -= cost
                        position_qty = qty
                        entry_price = fill_price
                        entry_date = bar_date
                        entry_index = i

            elif sig.signal == SignalType.SELL and position_qty > 0:
                fill_price = bar_open * (1 - slippage_pct)   # sell: receive less
                proceeds = position_qty * fill_price - fee_per_trade
                pnl = proceeds - (position_qty * entry_price) - fee_per_trade
                pnl_pct = (fill_price - entry_price) / entry_price if entry_price else 0.0
                slip_cost = position_qty * bar_open * slippage_pct
                holding_days = i - entry_index

                trades.append(BacktestTrade(
                    entry_date=entry_date, exit_date=bar_date, side="long",
                    entry_price=round(entry_price, 4),
                    exit_price=round(fill_price, 4),
                    qty=position_qty,
                    pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 4),
                    fee=round(fee_per_trade * 2, 2),   # entry + exit
                    slippage=round(slip_cost, 2),
                    holding_days=holding_days,
                ))

                cash += proceeds
                position_qty = 0
                entry_price = 0.0
                entry_date = ""

        # ── Close any remaining open position at last close ───────────────────
        if position_qty > 0:
            last_close = float(df["close"].iloc[-1])
            last_date = str(df.index[-1])[:10]
            fill_price = last_close * (1 - slippage_pct)
            proceeds = position_qty * fill_price - fee_per_trade
            pnl = proceeds - (position_qty * entry_price) - fee_per_trade
            pnl_pct = (fill_price - entry_price) / entry_price if entry_price else 0.0
            slip_cost = position_qty * last_close * slippage_pct
            holding_days = len(df) - 1 - entry_index

            trades.append(BacktestTrade(
                entry_date=entry_date, exit_date=last_date, side="long",
                entry_price=round(entry_price, 4),
                exit_price=round(fill_price, 4),
                qty=position_qty,
                pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 4),
                fee=round(fee_per_trade * 2, 2),
                slippage=round(slip_cost, 2),
                holding_days=holding_days,
            ))
            cash += proceeds
            position_qty = 0

        # ── 3. Compute metrics ────────────────────────────────────────────────
        final_capital = cash
        total_return = final_capital - initial_capital
        total_return_pct = total_return / initial_capital if initial_capital else 0.0

        winning = [t for t in trades if t.pnl > 0]
        losing  = [t for t in trades if t.pnl <= 0]
        num_trades = len(trades)
        win_rate   = len(winning) / num_trades if num_trades else 0.0
        avg_profit = sum(t.pnl for t in winning) / len(winning) if winning else 0.0
        avg_loss   = sum(t.pnl for t in losing)  / len(losing)  if losing  else 0.0
        avg_pnl    = sum(t.pnl for t in trades)  / num_trades   if num_trades else 0.0

        total_fees     = sum(t.fee for t in trades)
        total_slippage = sum(t.slippage for t in trades)
        avg_holding    = (
            sum(t.holding_days for t in trades) / num_trades if num_trades else 0.0
        )

        # Consecutive losses
        max_consec_loss = self._consecutive_losses(trades)

        # Drawdown
        max_dd, max_dd_pct = self._max_drawdown(equity_curve)

        # Worst single day
        worst_day_pnl, worst_day_date = self._worst_day(equity_curve, dates)

        # Ratios
        sharpe  = self._sharpe_ratio(equity_curve)
        sortino = self._sortino_ratio(equity_curve)
        calmar  = (total_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0

        # Profit factor
        gross_win  = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        result = BacktestResult(
            total_return=round(total_return, 2),
            total_return_pct=round(total_return_pct * 100, 4),
            win_rate=round(win_rate * 100, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct * 100, 4),
            num_trades=num_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            avg_profit=round(avg_profit, 2),
            avg_loss=round(avg_loss, 2),
            avg_pnl=round(avg_pnl, 2),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            calmar_ratio=round(calmar, 4),
            profit_factor=round(profit_factor, 4),
            worst_day_pnl=round(worst_day_pnl, 2),
            worst_day_date=worst_day_date,
            consecutive_losing_trades=max_consec_loss,
            avg_holding_days=round(avg_holding, 1),
            total_fees=round(total_fees, 2),
            total_slippage=round(total_slippage, 2),
            equity_curve=equity_curve,
            dates=dates,
            trades=trades,
            initial_capital=initial_capital,
            final_capital=round(final_capital, 2),
        )

        logger.info(
            "Backtest done: %d trades, return=%.2f%%, Sharpe=%.2f, "
            "maxDD=%.2f%%, fees=$%.2f, slippage=$%.2f",
            num_trades, total_return_pct * 100, sharpe,
            max_dd_pct * 100, total_fees, total_slippage,
        )
        return result

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _max_drawdown(equity_curve: List[float]) -> Tuple[float, float]:
        if not equity_curve:
            return 0.0, 0.0
        peak = equity_curve[0]
        max_dd = max_dd_pct = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = peak - v
            dd_pct = dd / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
        return max_dd, max_dd_pct

    @staticmethod
    def _sharpe_ratio(
        equity_curve: List[float],
        risk_free_rate: float = 0.0,
        periods: int = 252,
    ) -> float:
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=float)
        returns = np.diff(arr) / np.where(arr[:-1] == 0, 1, arr[:-1])
        mean = float(np.mean(returns)) - risk_free_rate / periods
        std  = float(np.std(returns, ddof=1))
        if std == 0 or math.isnan(std):
            return 0.0
        return mean / std * math.sqrt(periods)

    @staticmethod
    def _sortino_ratio(
        equity_curve: List[float],
        risk_free_rate: float = 0.0,
        periods: int = 252,
    ) -> float:
        if len(equity_curve) < 2:
            return 0.0
        arr = np.array(equity_curve, dtype=float)
        returns = np.diff(arr) / np.where(arr[:-1] == 0, 1, arr[:-1])
        mean = float(np.mean(returns)) - risk_free_rate / periods
        downside = returns[returns < 0]
        if len(downside) == 0:
            return 0.0
        downside_std = float(np.std(downside, ddof=1))
        if downside_std == 0 or math.isnan(downside_std):
            return 0.0
        return mean / downside_std * math.sqrt(periods)

    @staticmethod
    def _worst_day(
        equity_curve: List[float], dates: List[str]
    ) -> Tuple[float, str]:
        if len(equity_curve) < 2:
            return 0.0, ""
        worst = 0.0
        worst_date = ""
        for i in range(1, len(equity_curve)):
            change = equity_curve[i] - equity_curve[i - 1]
            if change < worst:
                worst = change
                worst_date = dates[i] if i < len(dates) else ""
        return worst, worst_date

    @staticmethod
    def _consecutive_losses(trades: List[BacktestTrade]) -> int:
        max_consec = 0
        current = 0
        for t in trades:
            if t.pnl <= 0:
                current += 1
                max_consec = max(max_consec, current)
            else:
                current = 0
        return max_consec

    @staticmethod
    def _empty_result(initial_capital: float) -> BacktestResult:
        return BacktestResult(
            total_return=0.0, total_return_pct=0.0, win_rate=0.0,
            max_drawdown=0.0, max_drawdown_pct=0.0, num_trades=0,
            winning_trades=0, losing_trades=0, avg_profit=0.0, avg_loss=0.0,
            avg_pnl=0.0, sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
            profit_factor=0.0, worst_day_pnl=0.0, worst_day_date="",
            consecutive_losing_trades=0, avg_holding_days=0.0,
            total_fees=0.0, total_slippage=0.0,
            equity_curve=[initial_capital], dates=[], trades=[],
            initial_capital=initial_capital, final_capital=initial_capital,
        )

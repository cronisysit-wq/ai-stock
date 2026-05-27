"""
Day Trading Agent — autonomous scan → size → enter → monitor → exit loop.

Broker-style session rules
--------------------------
* Targets scale with account (% of equity primary; optional USD floor).
* Max concurrent positions (default 3).
* Stop-loss + take-profit on every trade (minimum 1:2 R:R).
* Flat all positions before market close (day-trade discipline).
* Stop new entries when daily profit target OR max loss hit.
* All orders pass RiskManager + TradeExecutor gates.

Phases (US/Eastern)
-------------------
PRE_MARKET | OPEN | MIDDAY | POWER_HOUR | CLOSED

NOT FINANCIAL ADVICE.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, time, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from config.settings import get_settings
from trading.day_trade_sizer import DayTradeSizer, DayTradeSizingResult
from trading.executor import TradeExecutor, TradingMode, ExecutionResult
from trading.market_data import get_latest_price
from trading.strategies import SignalResult, SignalType

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PRE_MARKET_START = time(4, 0)


class SessionPhase(str, Enum):
    PRE_MARKET = "pre_market"
    OPEN = "open"
    MIDDAY = "midday"
    POWER_HOUR = "power_hour"
    CLOSED = "closed"


class AgentStatus(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    TRADING = "trading"
    TARGET_HIT = "target_hit"
    MAX_LOSS = "max_loss"
    HALTED = "halted"
    CLOSED = "closed"


@dataclass
class DayTradingAgentConfig:
    """Scalable agent configuration — percentages drive sizing at any account size."""
    account_equity: float
    preset: str = "day_trading"
    top_n: int = 30

    # Scalable daily targets (% of equity — supports 0.75% up to 20%+)
    daily_profit_target_pct: float = 0.75
    daily_profit_target_usd: Optional[float] = None
    daily_max_loss_pct: float = 1.5

    risk_per_trade_pct: float = 0.75
    max_trades_per_day: int = 8
    max_open_positions: int = 3
    min_setup_score: float = 68.0
    min_volume_ratio: float = 1.3

    stop_loss_pct: float = 1.0
    risk_reward_ratio: float = 2.0
    flat_before_close_minutes: int = 15

    # Auto-entry robustness gates
    min_composite_auto: float = 72.0
    min_sentiment_score: float = 48.0
    block_bearish_market: bool = True
    max_market_bearish_pct: float = 55.0
    loss_cooldown_minutes: int = 15
    enable_trailing_stop: bool = True
    trailing_stop_pct: float = 0.5

    # Sentiment + institutional AI
    enable_sentiment: bool = True
    advisor_persona: str = "warren_buffett"

    @property
    def daily_profit_target(self) -> float:
        pct_val = self.account_equity * self.daily_profit_target_pct / 100
        if self.daily_profit_target_usd and self.daily_profit_target_usd > 0:
            return max(pct_val, self.daily_profit_target_usd)
        return pct_val

    @property
    def daily_max_loss(self) -> float:
        # Scale max loss with target aggressiveness (cap at 50% of target or configured max)
        adaptive = min(
            self.daily_max_loss_pct,
            max(1.0, self.daily_profit_target_pct * 0.5),
        )
        return self.account_equity * adaptive / 100

    @property
    def target_aggressiveness(self) -> str:
        p = self.daily_profit_target_pct
        if p >= 15:
            return "EXTREME"
        if p >= 10:
            return "VERY_HIGH"
        if p >= 5:
            return "HIGH"
        if p >= 3:
            return "ACTIVE"
        return "MODERATE"


@dataclass
class OpenDayTrade:
    """Tracked intraday position with exit levels."""
    ticker: str
    side: str
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    score: float = 0.0
    risk_usd: float = 0.0
    reward_usd: float = 0.0
    high_water_mark: float = 0.0
    trailing_stop_pct: float = 0.0
    enable_trailing: bool = False

    def __post_init__(self) -> None:
        if self.high_water_mark <= 0:
            self.high_water_mark = self.entry_price

    def check_exit(self, current_price: float) -> Optional[str]:
        if self.side == "buy":
            if current_price > self.high_water_mark:
                self.high_water_mark = current_price
            if self.enable_trailing and self.trailing_stop_pct > 0:
                profit_pct = (self.high_water_mark - self.entry_price) / self.entry_price * 100
                if profit_pct >= 0.3:
                    trail_level = self.high_water_mark * (1 - self.trailing_stop_pct / 100)
                    if current_price <= trail_level:
                        return "trailing_stop"
            if current_price <= self.stop_loss:
                return "stop_loss"
            if current_price >= self.take_profit:
                return "take_profit"
        elif self.side == "sell":
            if current_price < self.high_water_mark or self.high_water_mark == self.entry_price:
                self.high_water_mark = current_price
            if self.enable_trailing and self.trailing_stop_pct > 0:
                profit_pct = (self.entry_price - self.high_water_mark) / self.entry_price * 100
                if profit_pct >= 0.3:
                    trail_level = self.high_water_mark * (1 + self.trailing_stop_pct / 100)
                    if current_price >= trail_level:
                        return "trailing_stop"
            if current_price >= self.stop_loss:
                return "stop_loss"
            if current_price <= self.take_profit:
                return "take_profit"
        return None


@dataclass
class TradeSetup:
    """Actionable day-trade setup after scan + sizing + sentiment."""
    ticker: str
    rank: int
    score: float
    signal: str
    price: float
    volume_ratio: float
    atr_pct: float
    sizing: DayTradeSizingResult
    explanation: str
    side: str = "buy"
    technical_score: float = 0.0
    sentiment_score: float = 50.0
    news_score: float = 50.0
    composite_score: float = 0.0
    sentiment_label: str = "NEUTRAL"
    analyst_consensus: str = "N/A"
    catalyst_notes: str = ""
    integrated: Any = None


@dataclass
class AgentCycleResult:
    """Full output of one agent cycle."""
    status: AgentStatus
    phase: SessionPhase
    config: DayTradingAgentConfig
    setups: List[TradeSetup] = field(default_factory=list)
    entries: List[Dict[str, Any]] = field(default_factory=list)
    exits: List[Dict[str, Any]] = field(default_factory=list)
    blocked: List[Dict[str, Any]] = field(default_factory=list)
    session_pnl: float = 0.0
    daily_target: float = 0.0
    target_progress_pct: float = 0.0
    open_positions: int = 0
    trades_today: int = 0
    message: str = ""
    scanned: int = 0
    integrated_analyses: List[Any] = field(default_factory=list)


class DayTradingAgent:
    """
    Professional day-trading agent.

    Manual mode: run_cycle(auto=False) → returns ranked setups for user approval.
    Auto mode:   run_cycle(auto=True)  → enters top setups via TradeExecutor.
    """

    def __init__(
        self,
        broker=None,
        risk_manager=None,
        executor: Optional[TradeExecutor] = None,
        config: Optional[DayTradingAgentConfig] = None,
    ) -> None:
        self.settings = get_settings()
        self.broker = broker
        self.risk_manager = risk_manager
        self.executor = executor
        self.config = config or DayTradingAgentConfig(account_equity=25_000.0)
        self.sizer = DayTradeSizer()
        self._open_trades: List[OpenDayTrade] = []
        self._session_date: Optional[date] = None
        self._realized_pnl: float = 0.0
        self._trades_today: int = 0
        self._last_universe_size: int = 0
        self._last_scanned: int = 0
        self._integrated_analyses: List[Any] = []
        self._last_loss_at: Optional[datetime] = None
        self._market_regime_note: str = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def run_cycle(
        self,
        auto: bool = False,
        kill_switch: bool = False,
        progress_callback=None,
    ) -> AgentCycleResult:
        """Execute one full agent cycle: exits → scan → (optional) entries."""
        self._roll_session()
        cfg = self.config
        phase = get_session_phase()
        result = AgentCycleResult(
            status=AgentStatus.IDLE,
            phase=phase,
            config=cfg,
            session_pnl=self._realized_pnl,
            daily_target=cfg.daily_profit_target,
            trades_today=self._trades_today,
            open_positions=len(self._open_trades),
        )

        if kill_switch or (self.risk_manager and self.risk_manager.kill_switch_engaged):
            result.status = AgentStatus.HALTED
            result.message = "Kill switch engaged — agent halted."
            return result

        if phase == SessionPhase.CLOSED:
            result.status = AgentStatus.CLOSED
            result.message = "Market closed (US/Eastern regular hours)."
            return result

        # Daily P&L gates
        if self._realized_pnl >= cfg.daily_profit_target:
            result.status = AgentStatus.TARGET_HIT
            result.target_progress_pct = 100.0
            result.message = f"Daily profit target ${cfg.daily_profit_target:,.2f} reached — no new entries."
            result.exits = self._monitor_exits(flat_eod=True)
            return result

        if self._realized_pnl <= -cfg.daily_max_loss:
            result.status = AgentStatus.MAX_LOSS
            result.message = f"Daily max loss ${cfg.daily_max_loss:,.2f} hit — agent stopped."
            result.exits = self._flatten_all(reason="max_loss")
            return result

        result.target_progress_pct = min(
            100.0, max(0.0, self._realized_pnl / cfg.daily_profit_target * 100)
        ) if cfg.daily_profit_target > 0 else 0.0

        # 1. Monitor / exit open trades first
        flat_eod = minutes_to_close() <= cfg.flat_before_close_minutes
        result.exits = self._monitor_exits(flat_eod=flat_eod)
        result.open_positions = len(self._open_trades)

        if flat_eod:
            result.message = "EOD flatten window — no new entries."
            result.status = AgentStatus.CLOSED
            return result

        if self._trades_today >= cfg.max_trades_per_day:
            result.message = f"Max trades/day ({cfg.max_trades_per_day}) reached."
            return result

        if len(self._open_trades) >= cfg.max_open_positions:
            result.message = f"Max open positions ({cfg.max_open_positions}) — waiting for exits."
            return result

        if self._in_loss_cooldown():
            remaining = self._loss_cooldown_remaining_min()
            result.message = f"Loss cooldown active — {remaining:.0f} min remaining before new entries."
            return result

        # 2. Scan universe
        result.status = AgentStatus.SCANNING
        setups = self._scan_and_rank(progress_callback)
        result.setups = setups
        result.scanned = self._last_scanned
        result.universe_size = self._last_universe_size
        result.integrated_analyses = list(self._integrated_analyses)
        result.message = f"Found {len(setups)} actionable setups from {self._last_universe_size} stocks."

        if not auto:
            result.status = AgentStatus.IDLE
            return result

        # 3. Auto-enter top setups
        if not self.settings.ENABLE_AUTO_MODE and not self.settings.is_live_auto_trading_allowed:
            result.message = "Auto disabled — set ENABLE_AUTO_MODE=true for paper auto."
            result.status = AgentStatus.IDLE
            return result

        if not self.executor:
            result.message = "Executor not initialized."
            return result

        market_ok, market_msg = self._market_regime_allows_long()
        if not market_ok:
            result.message = market_msg
            result.status = AgentStatus.IDLE
            return result

        result.status = AgentStatus.TRADING
        slots = cfg.max_open_positions - len(self._open_trades)
        max_new = min(slots, cfg.max_trades_per_day - self._trades_today)

        for setup in setups[:max_new]:
            if len(self._open_trades) >= cfg.max_open_positions:
                break
            if self._trades_today >= cfg.max_trades_per_day:
                break
            if setup.sizing.shares <= 0:
                continue

            gate_ok, gate_reason = self._passes_auto_entry_gates(setup)
            if not gate_ok:
                result.blocked.append({
                    "success": False,
                    "ticker": setup.ticker,
                    "message": gate_reason,
                    "score": setup.score,
                })
                continue

            entry = self._enter_setup(setup, auto=True)
            if entry.get("success"):
                result.entries.append(entry)
            else:
                result.blocked.append(entry)

        result.open_positions = len(self._open_trades)
        result.trades_today = self._trades_today
        result.session_pnl = self._realized_pnl
        result.message = (
            f"Cycle done: {len(result.entries)} entries, "
            f"{len(result.exits)} exits, {len(result.blocked)} blocked."
        )
        return result

    def enter_manual(self, setup: TradeSetup, kill_switch: bool = False) -> Dict[str, Any]:
        """Manual entry for a user-selected setup."""
        if kill_switch:
            return {"success": False, "message": "Kill switch active."}
        return self._enter_setup(setup, auto=False)

    def get_open_trades(self) -> List[OpenDayTrade]:
        return list(self._open_trades)

    def get_session_summary(self) -> Dict[str, Any]:
        cfg = self.config
        return {
            "session_date": str(self._session_date),
            "phase": get_session_phase().value,
            "realized_pnl": round(self._realized_pnl, 2),
            "daily_target": round(cfg.daily_profit_target, 2),
            "daily_target_pct": cfg.daily_profit_target_pct,
            "max_loss": round(cfg.daily_max_loss, 2),
            "target_progress_pct": round(
                min(100, self._realized_pnl / cfg.daily_profit_target * 100)
                if cfg.daily_profit_target else 0, 1
            ),
            "trades_today": self._trades_today,
            "open_positions": len(self._open_trades),
            "account_equity": cfg.account_equity,
        }

    # ── Scan & rank ───────────────────────────────────────────────────────────

    def _scan_and_rank(self, progress_callback=None) -> List[TradeSetup]:
        from analysis.market_scanner import MarketScanner

        cfg = self.config
        phase = get_session_phase()
        min_score = self._phase_min_score(phase)
        scanner = MarketScanner(
            max_workers=20,
            min_price=3.0,
            min_avg_volume=500_000,
            top_n=cfg.top_n,
            stop_loss_pct=cfg.stop_loss_pct,
            take_profit_pct=cfg.stop_loss_pct * cfg.risk_reward_ratio,
        )
        session = scanner.scan(preset=cfg.preset, progress_callback=progress_callback)
        self._last_universe_size = session.universe_size
        self._last_scanned = session.scanned

        held = {t.ticker for t in self._open_trades}
        setups: List[TradeSetup] = []
        raw_items = []
        for r in session.results:
            if not r.is_valid or r.ticker in held:
                continue
            if r.signal != "BUY_CANDIDATE":
                continue
            if r.overall_score < min_score:
                continue
            if r.volume_ratio < cfg.min_volume_ratio:
                continue
            if not (1.0 <= r.atr_pct <= 7.0):
                continue
            raw_items.append(r)

        # Sentiment + news enrichment (persona-weighted composite)
        integrated_list: List[Any] = []
        if cfg.enable_sentiment and raw_items:
            try:
                from analysis.integrated_analysis import IntegratedAnalyzer
                from ai.institutional_advisor import AdvisorPersona, get_persona_weights

                try:
                    persona = AdvisorPersona(cfg.advisor_persona)
                except ValueError:
                    persona = AdvisorPersona.BUFFETT
                tw, sw, nw = get_persona_weights(persona)

                enrich_items = [
                    {
                        "ticker": r.ticker,
                        "price": r.price,
                        "technical_score": r.overall_score,
                        "signal": r.signal,
                        "explanation": r.explanation,
                        "volume_ratio": r.volume_ratio,
                        "atr_pct": r.atr_pct,
                    }
                    for r in raw_items[: cfg.top_n]
                ]
                integrated_list = IntegratedAnalyzer(max_workers=8).enrich_batch(
                    enrich_items,
                    technical_weight=tw,
                    sentiment_weight=sw,
                    news_weight=nw,
                    progress_callback=progress_callback,
                )
            except Exception as exc:
                logger.warning("Sentiment enrichment failed: %s", exc)

        integrated_by_ticker = {ia.ticker: ia for ia in integrated_list}

        for r in raw_items:
            atr_dollars = r.price * r.atr_pct / 100 if r.atr_pct else None
            sizing = self.sizer.size(
                entry_price=r.price,
                account_equity=cfg.account_equity,
                atr_pct=r.atr_pct,
                atr_dollars=atr_dollars,
                stop_loss_pct=cfg.stop_loss_pct,
                risk_reward_ratio=cfg.risk_reward_ratio,
                risk_per_trade_pct=min(cfg.risk_per_trade_pct, 2.0),
            )
            if sizing.shares <= 0:
                continue

            ia = integrated_by_ticker.get(r.ticker)
            composite = ia.composite_score if ia else r.overall_score
            tech = ia.technical_score if ia else r.overall_score

            if ia and ia.sentiment_label == "BEARISH" and ia.sentiment_score < 42:
                continue
            if ia and ia.news_score < 35 and ia.sentiment_score < 45:
                continue

            setups.append(TradeSetup(
                ticker=r.ticker,
                rank=r.rank,
                score=composite,
                signal=r.signal,
                price=r.price,
                volume_ratio=r.volume_ratio,
                atr_pct=r.atr_pct,
                sizing=sizing,
                explanation=r.explanation,
                technical_score=tech,
                sentiment_score=ia.sentiment_score if ia else 50.0,
                news_score=ia.news_score if ia else 50.0,
                composite_score=composite,
                sentiment_label=ia.sentiment_label if ia else "NEUTRAL",
                analyst_consensus=ia.analyst_consensus if ia else "N/A",
                catalyst_notes=ia.catalyst_notes if ia else "",
                integrated=ia,
            ))

        setups.sort(key=lambda s: s.composite_score or s.score, reverse=True)
        for i, s in enumerate(setups, start=1):
            s.rank = i
        self._integrated_analyses = integrated_list
        return setups

    # ── Entries & exits ───────────────────────────────────────────────────────

    def _enter_setup(self, setup: TradeSetup, auto: bool) -> Dict[str, Any]:
        cfg = self.config
        qty = float(setup.sizing.shares)
        mode = (
            TradingMode.LIVE_AUTO if self.settings.is_live_auto_trading_allowed
            else TradingMode.AUTO_PAPER if auto
            else TradingMode.SEMI_AUTO
        )

        signal = SignalResult(
            signal=SignalType.BUY if setup.side == "buy" else SignalType.SELL,
            confidence=min(setup.score / 100, 1.0),
            strategy=f"day_agent:{cfg.preset}",
            explanation=setup.explanation[:500],
            indicators={"score": setup.score, "volume_ratio": setup.volume_ratio},
        )

        if not self.executor:
            return {"success": False, "ticker": setup.ticker, "message": "No executor"}

        exec_result: ExecutionResult = self.executor.execute_signal(
            signal=signal, ticker=setup.ticker, qty=qty, mode=mode,
        )

        if auto and exec_result.success and exec_result.action_taken == "order_placed":
            self._register_open(setup, qty)
            self._trades_today += 1
            self._log_audit("AGENT_ENTRY", setup.ticker, qty, setup.sizing)

        return {
            "success": exec_result.success and exec_result.action_taken == "order_placed",
            "ticker": setup.ticker,
            "qty": qty,
            "action": exec_result.action_taken,
            "message": exec_result.message,
            "score": setup.score,
            "risk_usd": setup.sizing.risk_usd,
            "reward_usd": setup.sizing.reward_usd,
        }

    def _register_open(self, setup: TradeSetup, qty: float) -> None:
        cfg = self.config
        self._open_trades.append(OpenDayTrade(
            ticker=setup.ticker,
            side=setup.side,
            qty=qty,
            entry_price=setup.price,
            stop_loss=setup.sizing.stop_loss,
            take_profit=setup.sizing.take_profit,
            opened_at=datetime.now(timezone.utc),
            score=setup.score,
            risk_usd=setup.sizing.risk_usd,
            reward_usd=setup.sizing.reward_usd,
            enable_trailing=cfg.enable_trailing_stop,
            trailing_stop_pct=cfg.trailing_stop_pct,
        ))

    def _monitor_exits(self, flat_eod: bool = False) -> List[Dict[str, Any]]:
        exits: List[Dict[str, Any]] = []
        remaining: List[OpenDayTrade] = []

        for trade in self._open_trades:
            price = self._current_price(trade.ticker)
            if price is None:
                remaining.append(trade)
                continue

            reason = "eod_flat" if flat_eod else trade.check_exit(price)
            if reason:
                ex = self._close_trade(trade, price, reason)
                exits.append(ex)
            else:
                remaining.append(trade)

        self._open_trades = remaining
        return exits

    def _flatten_all(self, reason: str = "flatten") -> List[Dict[str, Any]]:
        exits = []
        for trade in list(self._open_trades):
            price = self._current_price(trade.ticker) or trade.entry_price
            exits.append(self._close_trade(trade, price, reason))
        self._open_trades.clear()
        return exits

    def _close_trade(self, trade: OpenDayTrade, price: float, reason: str) -> Dict[str, Any]:
        pnl = (price - trade.entry_price) * trade.qty
        if trade.side == "sell":
            pnl = -pnl

        if self.broker:
            try:
                self.broker.place_order(
                    symbol=trade.ticker, qty=trade.qty,
                    side="sell" if trade.side == "buy" else "buy",
                    order_type="market",
                )
            except Exception as exc:
                logger.warning("Exit order failed for %s: %s", trade.ticker, exc)

        self._realized_pnl += pnl
        if pnl < 0:
            self._last_loss_at = datetime.now(timezone.utc)
        self._log_audit("AGENT_EXIT", trade.ticker, trade.qty, {"reason": reason, "pnl": pnl})

        return {
            "ticker": trade.ticker,
            "reason": reason,
            "exit_price": price,
            "pnl": round(pnl, 2),
            "entry": trade.entry_price,
        }

    def _current_price(self, ticker: str) -> Optional[float]:
        if self.broker:
            try:
                for p in self.broker.get_positions():
                    if p.get("symbol") == ticker:
                        return float(p.get("current_price", 0)) or None
            except Exception:
                pass
        try:
            return get_latest_price(ticker)
        except Exception:
            return None

    def _roll_session(self) -> None:
        today = datetime.now(ET).date()
        if self._session_date != today:
            self._session_date = today
            self._realized_pnl = 0.0
            self._trades_today = 0
            self._open_trades.clear()
            self._last_loss_at = None
            self._market_regime_note = ""
            if self.broker:
                try:
                    acct = self.broker.get_account()
                    self.config.account_equity = float(acct.get("equity", self.config.account_equity))
                except Exception:
                    pass

    def _log_audit(self, event: str, ticker: str, qty: float, extra: Any) -> None:
        try:
            from db.database import get_db_session
            from db.models import AuditLog
            session = get_db_session()
            session.add(AuditLog(
                event_type=event,
                details=json.dumps({"ticker": ticker, "qty": qty, "extra": extra}),
                level="INFO",
                created_at=datetime.now(timezone.utc),
            ))
            session.commit()
            session.close()
        except Exception as exc:
            logger.debug("Audit log failed: %s", exc)

    def _phase_min_score(self, phase: SessionPhase) -> float:
        """Raise the bar in choppy or late-session phases."""
        base = self.config.min_setup_score
        bumps = {
            SessionPhase.PRE_MARKET: 8.0,
            SessionPhase.OPEN: 0.0,
            SessionPhase.MIDDAY: 3.0,
            SessionPhase.POWER_HOUR: 5.0,
            SessionPhase.CLOSED: 99.0,
        }
        return base + bumps.get(phase, 0.0)

    def _in_loss_cooldown(self) -> bool:
        return self._loss_cooldown_remaining_min() > 0

    def _loss_cooldown_remaining_min(self) -> float:
        if not self._last_loss_at or self.config.loss_cooldown_minutes <= 0:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self._last_loss_at).total_seconds() / 60
        return max(0.0, self.config.loss_cooldown_minutes - elapsed)

    def _market_regime_allows_long(self) -> tuple[bool, str]:
        """Block new longs on broad risk-off days."""
        cfg = self.config
        if not cfg.block_bearish_market:
            return True, ""

        try:
            import yfinance as yf
            tickers = ["SPY", "QQQ"]
            data = yf.download(tickers, period="2d", progress=False, threads=False)
            if data is None or data.empty:
                return True, ""

            down_count = 0
            for sym in tickers:
                try:
                    close = data["Close"][sym] if len(tickers) > 1 else data["Close"]
                    if len(close) >= 2:
                        chg = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2]) * 100
                        if chg <= -0.75:
                            down_count += 1
                except Exception:
                    continue

            if down_count >= 2:
                msg = "Market regime filter: SPY & QQQ both weak — long entries paused."
                self._market_regime_note = msg
                return False, msg

            if cfg.enable_sentiment:
                from analysis.us_market_sentiment import USMarketSentimentScanner
                session = USMarketSentimentScanner(max_workers=6).scan(
                    preset="day_trading", limit=25, progress_callback=None,
                )
                if session.market_bearish_pct >= cfg.max_market_bearish_pct:
                    msg = (
                        f"Market sentiment bearish ({session.market_bearish_pct:.0f}% names) "
                        f"— long entries paused."
                    )
                    self._market_regime_note = msg
                    return False, msg
        except Exception as exc:
            logger.debug("Market regime check skipped: %s", exc)

        return True, ""

    def _passes_auto_entry_gates(self, setup: TradeSetup) -> tuple[bool, str]:
        """Stricter gates for auto mode vs manual scan results."""
        cfg = self.config
        composite = setup.composite_score or setup.score

        if composite < cfg.min_composite_auto:
            return False, f"Composite {composite:.0f} below auto minimum {cfg.min_composite_auto:.0f}"

        if setup.sentiment_score < cfg.min_sentiment_score:
            return False, f"Sentiment {setup.sentiment_score:.0f} below minimum {cfg.min_sentiment_score:.0f}"

        if setup.sentiment_label == "BEARISH" and setup.sentiment_score < 50:
            return False, "Bearish sentiment — auto entry blocked"

        if setup.news_score < 38 and setup.sentiment_score < 50:
            return False, "Negative news + weak sentiment — auto entry blocked"

        consensus = (setup.analyst_consensus or "").lower()
        if "strong sell" in consensus:
            return False, f"Analyst consensus ({setup.analyst_consensus}) conflicts with setup"
        if consensus.strip() == "sell" and setup.sentiment_score < 55:
            return False, f"Analyst consensus ({setup.analyst_consensus}) conflicts with setup"

        return True, ""


# ── Market session helpers ────────────────────────────────────────────────────

def get_session_phase(now: Optional[datetime] = None) -> SessionPhase:
    """US/Eastern market phase."""
    now = now or datetime.now(ET)
    if now.weekday() >= 5:
        return SessionPhase.CLOSED
    t = now.time()
    if t < PRE_MARKET_START:
        return SessionPhase.CLOSED
    if t < MARKET_OPEN:
        return SessionPhase.PRE_MARKET
    if t < time(11, 30):
        return SessionPhase.OPEN
    if t < time(15, 0):
        return SessionPhase.MIDDAY
    if t < MARKET_CLOSE:
        return SessionPhase.POWER_HOUR
    return SessionPhase.CLOSED


def minutes_to_close(now: Optional[datetime] = None) -> float:
    now = now or datetime.now(ET)
    if now.weekday() >= 5:
        return 0.0
    close_dt = datetime.combine(now.date(), MARKET_CLOSE, tzinfo=ET)
    delta = (close_dt - now).total_seconds() / 60
    return max(0.0, delta)


def scale_targets_for_equity(
    equity: float,
    target_pct: float = 0.75,
    usd_floor: Optional[float] = None,
    risk_per_trade_pct: float = 0.75,
) -> Dict[str, float]:
    """Helper: show how targets scale at any account size."""
    pct_target = equity * target_pct / 100
    effective = max(pct_target, usd_floor or 0)
    max_loss_pct = min(1.5, max(1.0, target_pct * 0.5))
    return {
        "equity": equity,
        "target_pct": target_pct,
        "target_from_pct": round(pct_target, 2),
        "usd_floor": usd_floor or 0,
        "effective_daily_target": round(effective, 2),
        "max_loss_pct": max_loss_pct,
        "max_loss_usd": round(equity * max_loss_pct / 100, 2),
        "risk_per_trade_usd": round(equity * risk_per_trade_pct / 100, 2),
    }


@dataclass(frozen=True)
class DayTradingThresholdProfile:
    """Preset-tuned day-trading gates — scales with daily target aggressiveness."""
    label: str
    aggressiveness: str
    min_setup_score: float
    min_composite_auto: float
    min_sentiment_score: float
    min_volume_ratio: float
    max_trades_per_day: int
    max_open_positions: int
    risk_per_trade_pct: float
    daily_max_loss_pct: float
    loss_cooldown_minutes: int
    max_market_bearish_pct: float
    trailing_stop_pct: float
    stop_loss_pct: float
    notes: str

    def to_config_kwargs(self) -> Dict[str, Any]:
        return {
            "min_setup_score": self.min_setup_score,
            "min_composite_auto": self.min_composite_auto,
            "min_sentiment_score": self.min_sentiment_score,
            "min_volume_ratio": self.min_volume_ratio,
            "max_trades_per_day": self.max_trades_per_day,
            "max_open_positions": self.max_open_positions,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "daily_max_loss_pct": self.daily_max_loss_pct,
            "loss_cooldown_minutes": self.loss_cooldown_minutes,
            "max_market_bearish_pct": self.max_market_bearish_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "stop_loss_pct": self.stop_loss_pct,
        }


def resolve_day_trading_thresholds(daily_profit_target_pct: float) -> DayTradingThresholdProfile:
    """
    Map daily target % to tuned entry/exit/risk gates.

    Higher targets → more trades allowed but still sentiment + regime filtered.
    Lower targets → fewer, higher-quality setups only.
    """
    p = max(0.25, daily_profit_target_pct)

    if p < 1.5:
        return DayTradingThresholdProfile(
            label="Conservative",
            aggressiveness="MODERATE",
            min_setup_score=72.0,
            min_composite_auto=75.0,
            min_sentiment_score=52.0,
            min_volume_ratio=1.4,
            max_trades_per_day=5,
            max_open_positions=2,
            risk_per_trade_pct=0.5,
            daily_max_loss_pct=1.0,
            loss_cooldown_minutes=20,
            max_market_bearish_pct=50.0,
            trailing_stop_pct=0.4,
            stop_loss_pct=0.85,
            notes="Fewer, higher-conviction setups. Tight market filter.",
        )
    if p < 4.0:
        return DayTradingThresholdProfile(
            label="Active",
            aggressiveness="ACTIVE",
            min_setup_score=68.0,
            min_composite_auto=72.0,
            min_sentiment_score=48.0,
            min_volume_ratio=1.3,
            max_trades_per_day=8,
            max_open_positions=3,
            risk_per_trade_pct=0.75,
            daily_max_loss_pct=1.25,
            loss_cooldown_minutes=15,
            max_market_bearish_pct=55.0,
            trailing_stop_pct=0.5,
            stop_loss_pct=1.0,
            notes="Balanced scan — default day-trading profile for 3% targets.",
        )
    if p < 7.0:
        return DayTradingThresholdProfile(
            label="Aggressive",
            aggressiveness="HIGH",
            min_setup_score=65.0,
            min_composite_auto=70.0,
            min_sentiment_score=45.0,
            min_volume_ratio=1.25,
            max_trades_per_day=10,
            max_open_positions=3,
            risk_per_trade_pct=1.0,
            daily_max_loss_pct=1.5,
            loss_cooldown_minutes=12,
            max_market_bearish_pct=58.0,
            trailing_stop_pct=0.55,
            stop_loss_pct=1.1,
            notes="More entries; sentiment gates still block bearish names.",
        )
    if p < 12.0:
        return DayTradingThresholdProfile(
            label="High",
            aggressiveness="VERY_HIGH",
            min_setup_score=62.0,
            min_composite_auto=68.0,
            min_sentiment_score=42.0,
            min_volume_ratio=1.2,
            max_trades_per_day=12,
            max_open_positions=4,
            risk_per_trade_pct=1.25,
            daily_max_loss_pct=2.0,
            loss_cooldown_minutes=10,
            max_market_bearish_pct=60.0,
            trailing_stop_pct=0.6,
            stop_loss_pct=1.2,
            notes="10% target tier — wider stops, faster trailing, more slots.",
        )
    if p < 17.0:
        return DayTradingThresholdProfile(
            label="Very High",
            aggressiveness="VERY_HIGH",
            min_setup_score=60.0,
            min_composite_auto=66.0,
            min_sentiment_score=40.0,
            min_volume_ratio=1.15,
            max_trades_per_day=14,
            max_open_positions=4,
            risk_per_trade_pct=1.5,
            daily_max_loss_pct=2.5,
            loss_cooldown_minutes=8,
            max_market_bearish_pct=62.0,
            trailing_stop_pct=0.65,
            stop_loss_pct=1.3,
            notes="15% target tier — high velocity; regime filter still active.",
        )
    return DayTradingThresholdProfile(
        label="Extreme",
        aggressiveness="EXTREME",
        min_setup_score=58.0,
        min_composite_auto=64.0,
        min_sentiment_score=38.0,
        min_volume_ratio=1.1,
        max_trades_per_day=15,
        max_open_positions=5,
        risk_per_trade_pct=min(2.0, p * 0.1),
        daily_max_loss_pct=min(3.0, p * 0.15),
        loss_cooldown_minutes=5,
        max_market_bearish_pct=65.0,
        trailing_stop_pct=0.7,
        stop_loss_pct=1.4,
        notes="20%+ target — maximum activity; auto gates still require composite + sentiment.",
    )


def build_day_agent_config(
    account_equity: float,
    daily_profit_target_pct: float,
    *,
    preset: str = "day_trading",
    top_n: int = 30,
    daily_profit_target_usd: Optional[float] = None,
    min_setup_score_override: Optional[float] = None,
    advisor_persona: str = "warren_buffett",
    enable_sentiment: bool = True,
    settings=None,
) -> DayTradingAgentConfig:
    """Build agent config with preset-tuned thresholds."""
    profile = resolve_day_trading_thresholds(daily_profit_target_pct)
    kwargs = profile.to_config_kwargs()
    if min_setup_score_override is not None:
        kwargs["min_setup_score"] = min_setup_score_override

    if settings is not None:
        kwargs["max_open_positions"] = min(
            kwargs["max_open_positions"], settings.DAY_TRADE_MAX_OPEN_POSITIONS
        )
        flat_before = settings.DAY_TRADE_FLAT_BEFORE_CLOSE_MIN
        rr = settings.DAY_TRADE_RISK_REWARD
    else:
        flat_before = 15
        rr = 2.0

    return DayTradingAgentConfig(
        account_equity=account_equity,
        preset=preset,
        top_n=top_n,
        daily_profit_target_pct=daily_profit_target_pct,
        daily_profit_target_usd=daily_profit_target_usd,
        advisor_persona=advisor_persona,
        enable_sentiment=enable_sentiment,
        block_bearish_market=True,
        enable_trailing_stop=True,
        risk_reward_ratio=rr,
        flat_before_close_minutes=flat_before,
        **kwargs,
    )

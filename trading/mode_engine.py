"""
Trading Mode Engine — unified orchestration for two styles:

1. DAY_TRADING   — US-wide day-trade candidates (MarketScanner)
2. MONTHLY_INCOME — swing / monthly-quality picks (IncomeScanner)

Each style supports:
- MANUAL  — scan & show picks; user approves trades
- AUTO    — auto-execute top candidates (paper/mock by default)

Safety: all auto paths go through TradeExecutor + RiskManager.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from config.settings import get_settings
from trading.executor import TradeExecutor, TradingMode, ExecutionResult
from trading.strategies import SignalResult, SignalType
from trading.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class TradingStyle(str, Enum):
    DAY_TRADING = "day_trading"
    MONTHLY_INCOME = "monthly_income"


class ExecutionPreference(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


TRADING_STYLE_LABELS = {
    TradingStyle.DAY_TRADING: "🔥 Day Trading (US-wide)",
    TradingStyle.MONTHLY_INCOME: "💰 Monthly Income / Swing",
}

EXECUTION_LABELS = {
    ExecutionPreference.MANUAL: "👤 Manual — you pick & approve",
    ExecutionPreference.AUTO: "🤖 Auto — system trades top picks",
}


@dataclass
class CandidatePick:
    """Normalized pick from either scanner for UI / auto execution."""
    ticker: str
    rank: int
    price: float
    signal: str
    score: float
    side: str = "buy"
    quantity: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    explanation: str = ""
    est_daily_usd: float = 0.0
    source: str = ""
    raw: Any = None


@dataclass
class ModeScanResult:
    """Unified scan output."""
    style: TradingStyle
    preset: str
    candidates: List[CandidatePick]
    universe_size: int
    scanned: int
    elapsed_seconds: float = 0.0
    daily_target_usd: float = 0.0
    session_id: str = ""
    disclaimer: str = ""
    integrated_analyses: List[Any] = field(default_factory=list)


@dataclass
class AutoRunResult:
    """Outcome of an auto-execution pass."""
    executed: List[Dict[str, Any]] = field(default_factory=list)
    blocked: List[Dict[str, Any]] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""


class TradingModeEngine:
    """
    Runs scans and optional auto-execution for day-trading or income mode.
    """

    def __init__(
        self,
        broker=None,
        risk_manager=None,
        executor: Optional[TradeExecutor] = None,
    ) -> None:
        self.settings = get_settings()
        self.broker = broker
        self.risk_manager = risk_manager
        self.executor = executor
        self.sizer = PositionSizer()

    # ── Scanning ──────────────────────────────────────────────────────────────

    def scan(
        self,
        style: TradingStyle,
        preset: Optional[str] = None,
        top_n: int = 25,
        daily_target_usd: float = 150.0,
        account_equity: float = 25_000.0,
        progress_callback=None,
        **scanner_kwargs,
    ) -> ModeScanResult:
        """Run the appropriate scanner for the trading style."""
        if style == TradingStyle.DAY_TRADING:
            return self._scan_day_trading(
                preset=preset or "day_trading",
                top_n=top_n,
                account_equity=account_equity,
                progress_callback=progress_callback,
                **scanner_kwargs,
            )
        return self._scan_monthly_income(
            preset=preset or "sp500",
            top_n=top_n,
            daily_target_usd=daily_target_usd,
            account_equity=account_equity,
            progress_callback=progress_callback,
            **scanner_kwargs,
        )

    def _scan_day_trading(
        self,
        preset: str,
        top_n: int,
        account_equity: float,
        progress_callback=None,
        daily_target_usd: float = 0.0,
        **kwargs,
    ) -> ModeScanResult:
        from trading.day_trading_agent import DayTradingAgent, build_day_agent_config

        usd_floor = daily_target_usd if daily_target_usd > 0 else None
        if usd_floor is None and self.settings.DAY_TRADE_DAILY_TARGET_USD > 0:
            usd_floor = self.settings.DAY_TRADE_DAILY_TARGET_USD

        target_pct = kwargs.get("daily_profit_target_pct", self.settings.DAY_TRADE_DAILY_TARGET_PCT)
        agent = DayTradingAgent(
            broker=self.broker,
            risk_manager=self.risk_manager,
            executor=self.executor,
            config=build_day_agent_config(
                account_equity=account_equity,
                daily_profit_target_pct=target_pct,
                preset=preset,
                top_n=top_n,
                daily_profit_target_usd=usd_floor,
                min_setup_score_override=kwargs.get("min_setup_score"),
                advisor_persona=kwargs.get("advisor_persona", "warren_buffett"),
                enable_sentiment=kwargs.get("enable_sentiment", True),
                settings=self.settings,
            ),
        )
        cycle = agent.run_cycle(auto=False, progress_callback=progress_callback)

        candidates: List[CandidatePick] = []
        for i, setup in enumerate(cycle.setups, start=1):
            sz = setup.sizing
            candidates.append(CandidatePick(
                ticker=setup.ticker,
                rank=i,
                price=setup.price,
                signal=setup.signal,
                score=setup.composite_score or setup.score,
                quantity=float(sz.shares),
                stop_loss=sz.stop_loss,
                take_profit=sz.take_profit,
                explanation=setup.explanation,
                est_daily_usd=sz.reward_usd,
                source=f"day_agent:{preset}",
                raw=setup,
            ))

        return ModeScanResult(
            style=TradingStyle.DAY_TRADING,
            preset=preset,
            candidates=candidates,
            universe_size=cycle.universe_size,
            scanned=cycle.scanned,
            elapsed_seconds=0.0,
            daily_target_usd=agent.config.daily_profit_target,
            session_id="",
            disclaimer="Day agent: R-multiple sizing scales with account equity.",
            integrated_analyses=cycle.integrated_analyses or [],
        )

    def run_day_agent(
        self,
        auto: bool,
        account_equity: float,
        preset: str = "day_trading",
        kill_switch: bool = False,
        progress_callback=None,
        daily_profit_target_pct: Optional[float] = None,
        daily_profit_target_usd: Optional[float] = None,
        top_n: int = 30,
        min_setup_score: Optional[float] = None,
        advisor_persona: str = "warren_buffett",
        enable_sentiment: bool = True,
    ):
        """Run full day-trading agent cycle (manual or auto)."""
        from trading.day_trading_agent import DayTradingAgent, build_day_agent_config

        target_pct = daily_profit_target_pct or self.settings.DAY_TRADE_DAILY_TARGET_PCT
        usd = daily_profit_target_usd or (
            self.settings.DAY_TRADE_DAILY_TARGET_USD or None
        )
        cfg = build_day_agent_config(
            account_equity=account_equity,
            daily_profit_target_pct=target_pct,
            preset=preset,
            top_n=top_n,
            daily_profit_target_usd=usd,
            min_setup_score_override=min_setup_score,
            advisor_persona=advisor_persona,
            enable_sentiment=enable_sentiment,
            settings=self.settings,
        )
        agent = DayTradingAgent(
            broker=self.broker,
            risk_manager=self.risk_manager,
            executor=self.executor,
            config=cfg,
        )
        return agent.run_cycle(auto=auto, kill_switch=kill_switch, progress_callback=progress_callback)

    def _scan_monthly_income(
        self,
        preset: str,
        top_n: int,
        daily_target_usd: float,
        account_equity: float,
        progress_callback=None,
        **kwargs,
    ) -> ModeScanResult:
        from analysis.income_scanner import IncomeScanner

        scanner = IncomeScanner(
            max_workers=kwargs.get("max_workers", 10),
            min_price=kwargs.get("min_price", 15.0),
            top_n=top_n,
            stop_loss_pct=kwargs.get("stop_loss_pct", 2.0),
            take_profit_pct=kwargs.get("take_profit_pct", 5.0),
        )
        session = scanner.scan(
            preset=preset,
            daily_target_usd=daily_target_usd,
            account_equity=account_equity,
            progress_callback=progress_callback,
        )

        integrated_list: List[Any] = []
        enable_sentiment = kwargs.get("enable_sentiment", True)
        advisor_persona = kwargs.get("advisor_persona", "warren_buffett")
        if enable_sentiment and session.results:
            try:
                from analysis.integrated_analysis import IntegratedAnalyzer
                from ai.institutional_advisor import AdvisorPersona, get_persona_weights

                try:
                    persona = AdvisorPersona(advisor_persona)
                except ValueError:
                    persona = AdvisorPersona.BUFFETT
                tw, sw, nw = get_persona_weights(persona)
                enrich_items = [
                    {
                        "ticker": r.ticker,
                        "price": r.price,
                        "technical_score": r.income_score,
                        "signal": r.signal,
                        "explanation": r.explanation,
                        "volume_ratio": r.vol_ratio,
                        "atr_pct": r.atr_pct,
                    }
                    for r in session.results[:top_n]
                ]
                integrated_list = IntegratedAnalyzer(max_workers=6).enrich_batch(
                    enrich_items,
                    technical_weight=tw,
                    sentiment_weight=sw,
                    news_weight=nw,
                    progress_callback=progress_callback,
                )
                integrated_by_ticker = {ia.ticker: ia for ia in integrated_list}
                for r in session.results:
                    ia = integrated_by_ticker.get(r.ticker)
                    if ia:
                        r.income_score = ia.composite_score
                        setattr(r, "integrated", ia)
                session.results.sort(key=lambda x: x.income_score, reverse=True)
                for i, r in enumerate(session.results, start=1):
                    r.rank = i
            except Exception as exc:
                logger.warning("Income sentiment enrichment failed: %s", exc)

        candidates: List[CandidatePick] = []
        for r in session.results:
            if not r.is_valid:
                continue
            candidates.append(CandidatePick(
                ticker=r.ticker,
                rank=r.rank,
                price=r.price,
                signal=r.signal,
                score=r.income_score,
                quantity=r.suggested_shares,
                stop_loss=r.stop_loss_price,
                take_profit=r.take_profit_price,
                explanation=r.explanation,
                est_daily_usd=r.est_daily_conservative,
                source=f"income:{preset}",
                raw=r,
            ))

        return ModeScanResult(
            style=TradingStyle.MONTHLY_INCOME,
            preset=preset,
            candidates=candidates,
            universe_size=session.universe_size,
            scanned=session.scanned,
            elapsed_seconds=session.elapsed_seconds,
            daily_target_usd=daily_target_usd,
            session_id=session.session_id,
            disclaimer=getattr(session, "disclaimer", ""),
            integrated_analyses=integrated_list,
        )

    # ── Auto execution ────────────────────────────────────────────────────────

    def auto_execute(
        self,
        scan_result: ModeScanResult,
        max_trades: int = 3,
        min_score: float = 65.0,
        kill_switch: bool = False,
    ) -> AutoRunResult:
        """
        Auto-execute top BUY_CANDIDATE picks through TradeExecutor.

        Uses AUTO_PAPER unless live flags are set (then LIVE_AUTO with guards).
        """
        result = AutoRunResult()

        if kill_switch:
            result.message = "Kill switch engaged — auto trading halted."
            return result

        if not self.executor:
            result.message = "Executor not initialized."
            return result

        if not self.settings.ENABLE_AUTO_MODE and not self.settings.is_live_auto_trading_allowed:
            result.message = (
                "Auto mode disabled. Set ENABLE_AUTO_MODE=true in .env for paper/mock auto trading."
            )
            return result

        mode = TradingMode.LIVE_AUTO if self.settings.is_live_auto_trading_allowed else TradingMode.AUTO_PAPER

        actionable = [
            c for c in scan_result.candidates
            if c.signal == "BUY_CANDIDATE" and (c.score >= min_score) and c.quantity >= 1
        ][:max_trades]

        if not actionable:
            result.message = "No actionable BUY_CANDIDATE picks above score threshold."
            return result

        for pick in actionable:
            signal = SignalResult(
                signal=SignalType.BUY,
                confidence=min(pick.score / 100, 1.0),
                strategy=f"{scan_result.style.value}:{scan_result.preset}",
                explanation=pick.explanation[:500],
                indicators={"score": pick.score},
            )
            try:
                exec_result: ExecutionResult = self.executor.execute_signal(
                    signal=signal,
                    ticker=pick.ticker,
                    qty=pick.quantity,
                    mode=mode,
                )
                entry = {
                    "ticker": pick.ticker,
                    "qty": pick.quantity,
                    "score": pick.score,
                    "success": exec_result.success,
                    "action": exec_result.action_taken,
                    "message": exec_result.message,
                }
                if exec_result.success and exec_result.action_taken == "order_placed":
                    result.executed.append(entry)
                elif exec_result.action_taken == "blocked":
                    result.blocked.append(entry)
                else:
                    result.skipped.append(entry)
            except Exception as exc:
                result.blocked.append({
                    "ticker": pick.ticker,
                    "error": str(exc),
                })

        n = len(result.executed)
        result.message = f"Auto run complete: {n} order(s) placed, {len(result.blocked)} blocked."
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _size_quantity(
        self,
        price: float,
        stop_loss: float,
        account_equity: float,
        atr_pct: Optional[float] = None,
    ) -> float:
        if price <= 0:
            return 1.0
        sizing = self.sizer.calculate(
            current_price=price,
            account_equity=account_equity,
            stop_loss_price=stop_loss or price * 0.98,
            atr_pct=atr_pct,
        )
        return max(1.0, sizing.suggested_qty)

    @staticmethod
    def default_preset(style: TradingStyle) -> str:
        if style == TradingStyle.DAY_TRADING:
            return "day_trading"
        return "sp500"

    @staticmethod
    def presets_for_style(style: TradingStyle) -> Dict[str, str]:
        if style == TradingStyle.DAY_TRADING:
            from analysis.market_scanner import SCAN_PRESETS
            return dict(SCAN_PRESETS)
        from analysis.income_scanner import INCOME_PRESETS
        return dict(INCOME_PRESETS)

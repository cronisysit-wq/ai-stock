"""Tests for day trading agent and sizer."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from trading.day_trade_sizer import DayTradeSizer
from trading.day_trading_agent import (
    DayTradingAgent,
    DayTradingAgentConfig,
    OpenDayTrade,
    TradeSetup,
    get_session_phase,
    scale_targets_for_equity,
    resolve_day_trading_thresholds,
    build_day_agent_config,
    SessionPhase,
)
from trading.day_trade_sizer import DayTradeSizingResult


class TestDayTradeSizer:
    def test_scales_with_equity(self):
        from unittest.mock import MagicMock
        mock_settings = MagicMock(
            MAX_RISK_PER_TRADE_PERCENT=1.0,
            MAX_POSITION_SIZE=50_000.0,
            MAX_PORTFOLIO_ALLOCATION_PER_TICKER_PERCENT=50.0,
        )
        sizer = DayTradeSizer(settings=mock_settings)
        small = sizer.size(entry_price=100.0, account_equity=10_000, atr_pct=2.0)
        large = sizer.size(entry_price=100.0, account_equity=100_000, atr_pct=2.0)
        assert large.shares > small.shares
        assert large.risk_usd > small.risk_usd

    def test_reward_is_r_multiple_of_risk(self):
        sizer = DayTradeSizer()
        r = sizer.size(entry_price=50.0, account_equity=25_000, atr_pct=2.5, risk_reward_ratio=2.0)
        if r.shares > 0:
            assert r.reward_usd == pytest.approx(r.risk_usd * 2.0, rel=0.01)


class TestScaleTargets:
    def test_pct_scales_with_account(self):
        small = scale_targets_for_equity(10_000, target_pct=1.0)
        large = scale_targets_for_equity(100_000, target_pct=1.0)
        assert large["target_from_pct"] == 1000.0
        assert small["target_from_pct"] == 100.0

    def test_usd_floor_on_small_account(self):
        s = scale_targets_for_equity(5_000, target_pct=0.5, usd_floor=100.0)
        assert s["effective_daily_target"] == 100.0


class TestOpenDayTrade:
    def test_stop_loss_trigger(self):
        t = OpenDayTrade(
            ticker="AAPL", side="buy", qty=10, entry_price=100.0,
            stop_loss=98.0, take_profit=104.0,
            opened_at=datetime.now(),
        )
        assert t.check_exit(97.5) == "stop_loss"
        assert t.check_exit(105.0) == "take_profit"
        assert t.check_exit(101.0) is None


class TestDayTradingAgent:
    def test_config_daily_target_scales(self):
        cfg = DayTradingAgentConfig(account_equity=50_000, daily_profit_target_pct=1.0)
        assert cfg.daily_profit_target == 500.0

    def test_config_usd_floor(self):
        cfg = DayTradingAgentConfig(
            account_equity=10_000, daily_profit_target_pct=0.5,
            daily_profit_target_usd=100.0,
        )
        assert cfg.daily_profit_target == 100.0

    def test_kill_switch_halts_cycle(self):
        agent = DayTradingAgent(config=DayTradingAgentConfig(account_equity=25_000))
        result = agent.run_cycle(auto=False, kill_switch=True)
        assert "halted" in result.message.lower()

    def test_auto_entry_gates_block_weak_sentiment(self):
        agent = DayTradingAgent(config=DayTradingAgentConfig(account_equity=25_000))
        sizing = DayTradeSizingResult(
            shares=10, entry_price=100.0, stop_loss=98.0, take_profit=104.0,
            stop_distance=2.0, risk_usd=50, reward_usd=100, risk_reward_ratio=2.0,
            notional_usd=1000, risk_pct_of_equity=0.2, capped_by="none",
        )
        setup = TradeSetup(
            ticker="TEST", rank=1, score=80, signal="BUY_CANDIDATE", price=100.0,
            volume_ratio=1.5, atr_pct=2.0, sizing=sizing, explanation="test",
            sentiment_score=40, composite_score=80, sentiment_label="NEUTRAL",
            analyst_consensus="HOLD", news_score=50,
        )
        ok, reason = agent._passes_auto_entry_gates(setup)
        assert ok is False
        assert "sentiment" in reason.lower()

    def test_phase_min_score_rises_in_power_hour(self):
        agent = DayTradingAgent(config=DayTradingAgentConfig(account_equity=25_000, min_setup_score=68))
        assert agent._phase_min_score(SessionPhase.POWER_HOUR) == 73.0


class TestDayTradingThresholds:
    def test_conservative_preset_stricter_than_aggressive(self):
        conservative = resolve_day_trading_thresholds(0.75)
        aggressive = resolve_day_trading_thresholds(5.0)
        extreme = resolve_day_trading_thresholds(20.0)
        assert conservative.min_setup_score > aggressive.min_setup_score
        assert aggressive.max_trades_per_day > conservative.max_trades_per_day
        assert extreme.risk_per_trade_pct > conservative.risk_per_trade_pct

    def test_build_config_applies_profile(self):
        cfg = build_day_agent_config(50_000, daily_profit_target_pct=3.0)
        profile = resolve_day_trading_thresholds(3.0)
        assert cfg.min_setup_score == profile.min_setup_score
        assert cfg.min_composite_auto == profile.min_composite_auto
        assert cfg.daily_profit_target_pct == 3.0

    def test_preset_labels_cover_user_ranges(self):
        assert resolve_day_trading_thresholds(0.75).label == "Conservative"
        assert resolve_day_trading_thresholds(3.0).label == "Active"
        assert resolve_day_trading_thresholds(10.0).label == "High"
        assert resolve_day_trading_thresholds(20.0).label == "Extreme"

    def test_session_phase_weekday(self):
        # Just ensure function runs without error
        phase = get_session_phase()
        assert isinstance(phase, SessionPhase)

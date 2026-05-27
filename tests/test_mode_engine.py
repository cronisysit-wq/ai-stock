"""Tests for income scanner and trading mode engine."""

import pytest
from unittest.mock import MagicMock, patch

from analysis.income_scanner import IncomeScanner, IncomeScanResult, INCOME_PRESETS
from trading.mode_engine import (
    TradingModeEngine,
    TradingStyle,
    ExecutionPreference,
    CandidatePick,
    ModeScanResult,
)


class TestIncomeScanner:
    def test_income_presets_not_empty(self):
        assert len(INCOME_PRESETS) >= 3

    def test_income_scan_result_valid(self):
        r = IncomeScanResult(ticker="AAPL", price=180.0)
        assert r.is_valid

    def test_income_scan_result_invalid_on_error(self):
        r = IncomeScanResult(ticker="BAD", error="fail")
        assert not r.is_valid


class TestTradingModeEngine:
    def test_default_presets(self):
        assert TradingModeEngine.default_preset(TradingStyle.DAY_TRADING) == "day_trading"
        assert TradingModeEngine.default_preset(TradingStyle.MONTHLY_INCOME) == "sp500"

    def test_presets_for_day_trading(self):
        presets = TradingModeEngine.presets_for_style(TradingStyle.DAY_TRADING)
        assert "day_trading" in presets.values() or any("day" in v for v in presets.values())

    def test_presets_for_income(self):
        presets = TradingModeEngine.presets_for_style(TradingStyle.MONTHLY_INCOME)
        assert "sp500" in presets.values()

    def test_auto_execute_blocked_without_auto_mode(self):
        engine = TradingModeEngine(executor=MagicMock())
        scan = ModeScanResult(
            style=TradingStyle.DAY_TRADING,
            preset="day_trading",
            candidates=[
                CandidatePick(
                    ticker="AAPL", rank=1, price=180.0,
                    signal="BUY_CANDIDATE", score=80.0, quantity=5,
                ),
            ],
            universe_size=100,
            scanned=100,
        )
        with patch("trading.mode_engine.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_AUTO_MODE = False
            mock_settings.return_value.is_live_auto_trading_allowed = False
            result = engine.auto_execute(scan, kill_switch=False)
        assert "disabled" in result.message.lower() or len(result.executed) == 0

    def test_auto_execute_kill_switch(self):
        engine = TradingModeEngine(executor=MagicMock())
        scan = ModeScanResult(
            style=TradingStyle.DAY_TRADING,
            preset="day_trading",
            candidates=[],
            universe_size=0,
            scanned=0,
        )
        result = engine.auto_execute(scan, kill_switch=True)
        assert "kill switch" in result.message.lower()

    def test_execution_preference_enum(self):
        assert ExecutionPreference.MANUAL.value == "manual"
        assert ExecutionPreference.AUTO.value == "auto"

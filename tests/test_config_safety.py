"""
Tests for config safety — ensures safety defaults are locked.
6 critical tests that must always pass.
"""

import pytest
from config.settings import Settings


def make_settings(**overrides) -> Settings:
    defaults = dict(
        ALPACA_API_KEY="", ALPACA_SECRET_KEY="",
        ALPACA_BASE_URL="https://paper-api.alpaca.markets",
        ENABLE_LIVE_TRADING=False,
        ENABLE_AUTO_LIVE_TRADING=False,
        ENABLE_AUTO_MODE=False,
        MAX_DAILY_LOSS=100.0, MAX_POSITION_SIZE=500.0,
        MAX_TRADES_PER_DAY=5, STOP_LOSS_PCT=2.0,
        TAKE_PROFIT_PCT=5.0, COOLDOWN_SECONDS=300,
        REJECT_DUPLICATE_ORDERS=True,
        DUPLICATE_ORDER_WINDOW_SECONDS=60,
        REJECT_MARKET_CLOSED=True,
        DATABASE_URL="sqlite:///:memory:",
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestDefaultSafetyFlags:
    """All dangerous flags must default to False."""

    def test_live_trading_disabled_by_default(self):
        s = make_settings()
        assert s.ENABLE_LIVE_TRADING is False, \
            "ENABLE_LIVE_TRADING must default to False"

    def test_auto_live_trading_disabled_by_default(self):
        s = make_settings()
        assert s.ENABLE_AUTO_LIVE_TRADING is False, \
            "ENABLE_AUTO_LIVE_TRADING must default to False"

    def test_auto_mode_disabled_by_default(self):
        s = make_settings()
        assert s.ENABLE_AUTO_MODE is False, \
            "ENABLE_AUTO_MODE must default to False"


class TestLiveTradingLogic:
    def test_paper_url_is_not_live(self):
        s = make_settings(
            ALPACA_BASE_URL="https://paper-api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
        )
        assert s.is_paper_trading is True
        assert s.is_live_trading is False   # URL is paper despite flag

    def test_live_url_with_flag_enables_live(self):
        s = make_settings(
            ALPACA_BASE_URL="https://api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
        )
        assert s.is_live_trading is True

    def test_live_auto_requires_both_flags(self):
        # Only live flag set
        s1 = make_settings(
            ALPACA_BASE_URL="https://api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
            ENABLE_AUTO_LIVE_TRADING=False,
        )
        assert s1.is_live_auto_trading_allowed is False

        # Both flags set
        s2 = make_settings(
            ALPACA_BASE_URL="https://api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
            ENABLE_AUTO_LIVE_TRADING=True,
        )
        assert s2.is_live_auto_trading_allowed is True

    def test_mock_broker_used_when_no_keys(self):
        s = make_settings(ALPACA_API_KEY="", ALPACA_SECRET_KEY="")
        assert s.use_mock_broker is True

    def test_mock_broker_not_used_when_keys_present(self):
        s = make_settings(
            ALPACA_API_KEY="real_key_abc123",
            ALPACA_SECRET_KEY="real_secret_xyz456",
        )
        assert s.use_mock_broker is False
        assert s.has_alpaca_keys is True

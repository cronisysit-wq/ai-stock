"""
Unit tests for TradeExecutor — all 6 trading modes.

The broker and risk manager are fully mocked so tests are deterministic
and do not depend on external services.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from trading.executor import TradeExecutor, TradingMode, ExecutionResult
from trading.strategies import SignalResult, SignalType
from trading.risk_manager import RiskCheckResult
from config.settings import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_test_settings(**overrides) -> Settings:
    defaults = {
        "ALPACA_API_KEY": "test",
        "ALPACA_SECRET_KEY": "test",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ENABLE_LIVE_TRADING": False,
        "ENABLE_AUTO_LIVE_TRADING": False,
        "ENABLE_AUTO_MODE": False,
        "MAX_DAILY_LOSS": 100.0,
        "MAX_POSITION_SIZE": 500.0,
        "MAX_TRADES_PER_DAY": 5,
        "STOP_LOSS_PCT": 2.0,
        "TAKE_PROFIT_PCT": 5.0,
        "COOLDOWN_SECONDS": 300,
        "REJECT_DUPLICATE_ORDERS": True,
        "DUPLICATE_ORDER_WINDOW_SECONDS": 60,
        "REJECT_MARKET_CLOSED": False,
        "DATABASE_URL": "sqlite:///test.db",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _buy_signal() -> SignalResult:
    return SignalResult(
        signal=SignalType.BUY, confidence=0.85,
        strategy="test_strategy", explanation="Test buy signal",
        indicators={"sma_20": 105.0, "sma_50": 100.0},
    )

def _sell_signal() -> SignalResult:
    return SignalResult(
        signal=SignalType.SELL, confidence=0.80,
        strategy="test_strategy", explanation="Test sell signal",
        indicators={"rsi": 75.0},
    )

def _hold_signal() -> SignalResult:
    return SignalResult(
        signal=SignalType.HOLD, confidence=0.5,
        strategy="test_strategy", explanation="No action",
        indicators={},
    )

def _approved_risk_check() -> RiskCheckResult:
    return RiskCheckResult(
        approved=True,
        checks_passed=["position_size", "daily_loss", "trade_count"],
        checks_failed=[], details={},
    )

def _rejected_risk_check() -> RiskCheckResult:
    return RiskCheckResult(
        approved=False,
        checks_passed=["position_size"],
        checks_failed=["daily_loss_exceeded"],
        details={"daily_pnl": -150.0},
    )

def _mock_broker() -> MagicMock:
    broker = MagicMock()
    broker.place_order.return_value = {
        "id": "order-123", "status": "accepted",
        "symbol": "AAPL", "qty": 5, "side": "buy",
    }
    broker.get_account.return_value = {
        "equity": 100_000, "buying_power": 200_000,
        "cash": 100_000, "daily_pnl": 0,
    }
    type(broker).kill_switch_engaged = PropertyMock(return_value=False)
    return broker

def _mock_risk_manager(approved: bool = True) -> MagicMock:
    rm = MagicMock()
    if approved:
        rm.check_order.return_value = _approved_risk_check()
        rm.approve_trade.return_value = True
    else:
        rm.check_order.return_value = _rejected_risk_check()
        rm.approve_trade.return_value = False
    type(rm).kill_switch_engaged = PropertyMock(return_value=False)
    return rm


# ---------------------------------------------------------------------------
# Paper Modes
# ---------------------------------------------------------------------------

class TestManualMode:
    """MANUAL mode: display signals only, never place orders."""

    def test_manual_does_not_place_order(self):
        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.MANUAL,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "signal_displayed"

    def test_manual_sell_signal_display_only(self):
        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_sell_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.MANUAL,
        )
        broker.place_order.assert_not_called()
        assert result.success is True


class TestSemiAutoMode:
    """SEMI_AUTO mode: queue signals for user approval."""

    def test_semi_auto_queues_signal(self):
        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.SEMI_AUTO,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "queued"
        assert len(executor.pending_signals) == 1

    def test_semi_auto_approve_executes(self):
        broker = _mock_broker()
        rm = _mock_risk_manager(approved=True)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        # Queue signal
        executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.SEMI_AUTO,
        )
        sig_id = list(executor.pending_signals.keys())[0]

        # Approve it
        result = executor.approve_pending(sig_id, qty=5)
        assert result.action_taken == "order_placed"
        broker.place_order.assert_called_once()


class TestAutoPaperMode:
    """AUTO_PAPER mode: auto-execute on paper/mock if ENABLE_AUTO_MODE is set."""

    @patch("trading.executor.get_settings")
    def test_auto_paper_blocked_when_disabled(self, mock_settings):
        settings = create_test_settings(ENABLE_AUTO_MODE=False)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.AUTO_PAPER,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "blocked"
        assert result.success is False

    @patch("trading.executor.get_settings")
    def test_auto_paper_places_order_when_enabled(self, mock_settings):
        settings = create_test_settings(ENABLE_AUTO_MODE=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=True)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.AUTO_PAPER,
        )
        broker.place_order.assert_called_once()
        assert result.success is True
        assert result.action_taken == "order_placed"

    @patch("trading.executor.get_settings")
    def test_auto_paper_blocked_by_risk_check(self, mock_settings):
        settings = create_test_settings(ENABLE_AUTO_MODE=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=False)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.AUTO_PAPER,
        )
        broker.place_order.assert_not_called()
        assert result.success is False


# ---------------------------------------------------------------------------
# Live Modes
# ---------------------------------------------------------------------------

class TestLiveManualMode:
    """LIVE_MANUAL: display only — same as MANUAL but for live context."""

    @patch("trading.executor.get_settings")
    def test_live_manual_blocked_if_live_not_enabled(self, mock_settings):
        settings = create_test_settings(ENABLE_LIVE_TRADING=False)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_MANUAL,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "blocked"

    @patch("trading.executor.get_settings")
    def test_live_manual_displays_signal_when_enabled(self, mock_settings):
        settings = create_test_settings(ENABLE_LIVE_TRADING=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_MANUAL,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "signal_displayed"


class TestLiveSemiAutoMode:
    """LIVE_SEMI_AUTO: queue for approval, requires ENABLE_LIVE_TRADING."""

    @patch("trading.executor.get_settings")
    def test_live_semi_auto_blocked_without_flag(self, mock_settings):
        settings = create_test_settings(ENABLE_LIVE_TRADING=False)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_SEMI_AUTO,
        )
        assert result.action_taken == "blocked"

    @patch("trading.executor.get_settings")
    def test_live_semi_auto_queues_when_enabled(self, mock_settings):
        settings = create_test_settings(ENABLE_LIVE_TRADING=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_SEMI_AUTO,
        )
        assert result.action_taken == "queued"


class TestLiveAutoMode:
    """LIVE_AUTO: the most dangerous mode — requires BOTH flags."""

    @patch("trading.executor.get_settings")
    def test_live_auto_blocked_without_both_flags(self, mock_settings):
        # Only ENABLE_LIVE_TRADING set, missing ENABLE_AUTO_LIVE_TRADING
        settings = create_test_settings(
            ALPACA_BASE_URL="https://api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
            ENABLE_AUTO_LIVE_TRADING=False,
        )
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=True)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_AUTO,
        )
        broker.place_order.assert_not_called()
        assert result.action_taken == "blocked"
        assert "ENABLE_AUTO_LIVE_TRADING" in result.message

    @patch("trading.executor.get_settings")
    def test_live_auto_blocked_without_live_flag(self, mock_settings):
        settings = create_test_settings(
            ENABLE_LIVE_TRADING=False,
            ENABLE_AUTO_LIVE_TRADING=True,
        )
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_AUTO,
        )
        assert result.action_taken == "blocked"

    @patch("trading.executor.get_settings")
    def test_live_auto_places_order_when_both_flags_set(self, mock_settings):
        settings = create_test_settings(
            ALPACA_BASE_URL="https://api.alpaca.markets",
            ENABLE_LIVE_TRADING=True,
            ENABLE_AUTO_LIVE_TRADING=True,
        )
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=True)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.LIVE_AUTO,
        )
        broker.place_order.assert_called_once()
        assert result.success is True


# ---------------------------------------------------------------------------
# Shared behaviour across all modes
# ---------------------------------------------------------------------------

class TestHoldSignal:
    """HOLD signals should never trigger any order, regardless of mode."""

    @pytest.mark.parametrize("mode", list(TradingMode))
    def test_hold_never_places_order(self, mode):
        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_hold_signal(), ticker="AAPL", qty=5, mode=mode,
        )
        broker.place_order.assert_not_called()
        assert "signal_displayed" in result.action_taken


class TestApproveTradeGate:
    """The risk_manager.approve_trade() gate must be called before every auto order."""

    @patch("trading.executor.get_settings")
    def test_approve_trade_called_for_auto_paper(self, mock_settings):
        settings = create_test_settings(ENABLE_AUTO_MODE=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=True)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.AUTO_PAPER,
        )
        rm.approve_trade.assert_called()

    @patch("trading.executor.get_settings")
    def test_auto_order_rejected_when_approve_trade_false(self, mock_settings):
        settings = create_test_settings(ENABLE_AUTO_MODE=True)
        mock_settings.return_value = settings

        broker = _mock_broker()
        rm = _mock_risk_manager(approved=False)
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.execute_signal(
            signal=_buy_signal(), ticker="AAPL", qty=5,
            mode=TradingMode.AUTO_PAPER,
        )
        broker.place_order.assert_not_called()
        assert result.success is False


class TestPendingApprovalNonexistent:
    """Approving a signal that doesn't exist in the queue should fail gracefully."""

    def test_approve_nonexistent_fails(self):
        broker = _mock_broker()
        rm = _mock_risk_manager()
        executor = TradeExecutor(broker=broker, risk_manager=rm)

        result = executor.approve_pending(signal_id=99999, qty=5)
        assert result.success is False
        assert result.action_taken == "blocked"

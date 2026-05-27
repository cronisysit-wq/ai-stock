"""
Tests for MockBroker — 12 test cases covering all major scenarios.
"""

import pytest
from trading.mock_broker import MockBroker


@pytest.fixture
def broker():
    b = MockBroker(initial_capital=10_000.0, reject_unknown_tickers=False)
    b.set_price("AAPL", 150.0)
    b.set_price("MSFT", 300.0)
    return b


# ── Account ───────────────────────────────────────────────────────────────────

class TestMockBrokerAccount:
    def test_initial_account_values(self, broker):
        acc = broker.get_account()
        assert acc["cash"] == 10_000.0
        assert acc["portfolio_value"] == 10_000.0
        assert acc["is_mock"] is True
        assert acc["trading_blocked"] is False

    def test_account_after_buy(self, broker):
        broker.place_order("AAPL", 10, "buy")
        acc = broker.get_account()
        # Should have spent ~$1500 (10 × $150 + slippage)
        assert acc["cash"] < 10_000.0

    def test_portfolio_value_reflects_position(self, broker):
        broker.place_order("AAPL", 10, "buy")
        broker.set_price("AAPL", 200.0)   # price goes up
        acc = broker.get_account()
        # portfolio value should be higher than initial cash
        assert acc["portfolio_value"] > acc["cash"]


# ── Orders ────────────────────────────────────────────────────────────────────

class TestMockBrokerOrders:
    def test_market_buy_fills_immediately(self, broker):
        result = broker.place_order("AAPL", 5, "buy")
        assert result["status"] == "filled"
        assert result["filled_avg_price"] is not None

    def test_market_sell_fills_immediately(self, broker):
        broker.place_order("AAPL", 10, "buy")
        result = broker.place_order("AAPL", 5, "sell")
        assert result["status"] == "filled"

    def test_order_history_tracked(self, broker):
        broker.place_order("AAPL", 5, "buy")
        broker.place_order("MSFT", 2, "buy")
        orders = broker.get_orders(status="all")
        assert len(orders) == 2

    def test_cancel_order(self, broker):
        # Place a limit order (won't auto-fill)
        result = broker.place_order("AAPL", 5, "buy",
                                    order_type="limit", limit_price=100.0)
        order_id = result["id"]
        cancelled = broker.cancel_order(order_id)
        assert cancelled is True
        orders = broker.get_orders(status="cancelled")
        assert any(o["id"] == order_id for o in orders)

    def test_cancel_all_orders(self, broker):
        broker.place_order("AAPL", 1, "buy", order_type="limit", limit_price=50.0)
        broker.place_order("MSFT", 1, "buy", order_type="limit", limit_price=100.0)
        broker.cancel_all_orders()
        pending = broker.get_orders(status="new")
        assert len(pending) == 0


# ── Rejections ────────────────────────────────────────────────────────────────

class TestMockBrokerRejections:
    def test_reject_zero_quantity(self, broker):
        result = broker.place_order("AAPL", 0, "buy")
        assert result["status"] == "rejected"
        assert "Quantity" in result.get("error", "")

    def test_reject_negative_quantity(self, broker):
        result = broker.place_order("AAPL", -5, "buy")
        assert result["status"] == "rejected"

    def test_reject_insufficient_cash(self, broker):
        # Try to buy more than we can afford
        result = broker.place_order("AAPL", 10_000, "buy")
        assert result["status"] == "rejected"
        assert "Insufficient cash" in result.get("error", "")

    def test_reject_sell_without_position(self, broker):
        result = broker.place_order("AAPL", 5, "sell")
        assert result["status"] == "rejected"
        assert "Insufficient position" in result.get("error", "")

    def test_reject_when_kill_switch_engaged(self, broker):
        broker.engage_kill_switch()
        result = broker.place_order("AAPL", 1, "buy")
        assert result["status"] == "rejected"
        assert "Kill switch" in result.get("error", "")

    def test_reject_unknown_ticker(self):
        strict_broker = MockBroker(initial_capital=10_000, reject_unknown_tickers=True)
        result = strict_broker.place_order("FAKEXYZ", 1, "buy")
        assert result["status"] == "rejected"
        assert "Unknown ticker" in result.get("error", "")


# ── Positions ─────────────────────────────────────────────────────────────────

class TestMockBrokerPositions:
    def test_position_created_on_buy(self, broker):
        broker.place_order("AAPL", 10, "buy")
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["qty"] == 10

    def test_position_removed_on_full_sell(self, broker):
        broker.place_order("AAPL", 10, "buy")
        broker.place_order("AAPL", 10, "sell")
        positions = broker.get_positions()
        assert len(positions) == 0

    def test_partial_sell_reduces_position(self, broker):
        broker.place_order("AAPL", 10, "buy")
        broker.place_order("AAPL", 4, "sell")
        positions = broker.get_positions()
        assert positions[0]["qty"] == 6


# ── Kill Switch ───────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_kill_switch_blocks_all_orders(self, broker):
        broker.engage_kill_switch()
        assert broker.kill_switch_engaged is True
        result = broker.place_order("AAPL", 1, "buy")
        assert result["status"] == "rejected"

    def test_kill_switch_cancels_pending(self, broker):
        broker.place_order("AAPL", 1, "buy", order_type="limit", limit_price=50.0)
        broker.engage_kill_switch()
        orders = broker.get_orders(status="cancelled")
        assert len(orders) >= 1

    def test_disengage_allows_trading(self, broker):
        broker.engage_kill_switch()
        broker.disengage_kill_switch()
        result = broker.place_order("AAPL", 1, "buy")
        assert result["status"] == "filled"


# ── Reset ─────────────────────────────────────────────────────────────────────

class TestMockBrokerReset:
    def test_reset_clears_all_state(self, broker):
        broker.place_order("AAPL", 5, "buy")
        broker.reset(initial_capital=5_000.0)
        acc = broker.get_account()
        assert acc["cash"] == 5_000.0
        assert broker.order_count == 0
        assert len(broker.get_positions()) == 0

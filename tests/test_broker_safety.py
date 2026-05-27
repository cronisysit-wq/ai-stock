"""
Tests for broker safety controls.

Tests:
  1. RobinhoodWatchlistBroker.CAN_TRADE is always False
  2. RobinhoodWatchlistBroker.place_order raises NotImplementedError
  3. MockBroker kill switch blocks orders
  4. MockBroker CSV import adds tickers to watchlist (RobinhoodWatchlistBroker)
"""

import pytest
from unittest.mock import patch, MagicMock


class TestRobinhoodWatchlistBroker:

    def test_can_trade_is_false(self):
        """CAN_TRADE class attribute must be False — structural safety guarantee."""
        from brokers.robinhood_watchlist import RobinhoodWatchlistBroker
        broker = RobinhoodWatchlistBroker()
        assert broker.CAN_TRADE is False
        assert broker.__class__.CAN_TRADE is False

    def test_place_order_raises(self):
        """place_order must always raise NotImplementedError."""
        from brokers.robinhood_watchlist import RobinhoodWatchlistBroker
        broker = RobinhoodWatchlistBroker()
        with pytest.raises(NotImplementedError, match="cannot place orders"):
            broker.place_order(symbol="AAPL", qty=10, side="buy")

    def test_watchlist_add_remove(self):
        """add_ticker and remove_ticker must update watchlist."""
        from brokers.robinhood_watchlist import RobinhoodWatchlistBroker
        with patch("brokers.robinhood_watchlist.get_db_session") as mock_db_fn:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db_fn.return_value = mock_db
            broker = RobinhoodWatchlistBroker()
            broker.add_ticker("aapl")  # should uppercase
            assert "AAPL" in broker.get_watchlist()
            broker.remove_ticker("AAPL")
            assert "AAPL" not in broker.get_watchlist()

    def test_csv_import(self):
        """CSV import must parse Symbol column and add to watchlist."""
        from brokers.robinhood_watchlist import RobinhoodWatchlistBroker
        with patch("brokers.robinhood_watchlist.get_db_session") as mock_db_fn:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db_fn.return_value = mock_db
            broker = RobinhoodWatchlistBroker()
            csv_data = "Symbol,Name,Price\nAAPL,Apple Inc,150\nMSFT,Microsoft Corp,300\n"
            imported = broker.import_from_csv(csv_data)
            assert "AAPL" in imported
            assert "MSFT" in imported
            assert "AAPL" in broker.get_watchlist()


class TestMockBrokerKillSwitch:

    def test_kill_switch_blocks_orders(self):
        """MockBroker with kill switch engaged must reject place_order."""
        from trading.mock_broker import MockBroker
        broker = MockBroker(initial_capital=10000.0)
        broker.engage_kill_switch()
        with pytest.raises(Exception, match="[Kk]ill"):
            broker.place_order(symbol="AAPL", qty=10, side="buy")

    def test_kill_switch_can_disengage(self):
        """MockBroker disengaging kill switch must allow orders."""
        from trading.mock_broker import MockBroker
        broker = MockBroker(initial_capital=10000.0)
        broker.engage_kill_switch()
        broker.disengage_kill_switch()
        assert broker.kill_switch_engaged is False
        # Order should not raise (may fill or reject based on funds, but not kill-switch error)
        try:
            broker.place_order(symbol="AAPL", qty=1, side="buy")
        except Exception as e:
            assert "kill" not in str(e).lower(), f"Kill switch still blocking: {e}"

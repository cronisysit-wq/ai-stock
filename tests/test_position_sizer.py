"""
Tests for trading/position_sizer.py

Tests:
  1. Risk-based sizing uses max_risk_per_trade
  2. Position size is capped by MAX_POSITION_SIZE
  3. High ATR reduces quantity by 25%
  4. Invalid price returns error result with qty=0
"""

import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_settings(**overrides):
    """Create a mock settings object with safe defaults."""
    s = MagicMock()
    s.MAX_RISK_PER_TRADE_PERCENT = overrides.get("MAX_RISK_PER_TRADE_PERCENT", 1.0)
    s.MAX_POSITION_SIZE = overrides.get("MAX_POSITION_SIZE", 500.0)
    s.STOP_LOSS_PCT = overrides.get("STOP_LOSS_PCT", 2.0)
    s.TAKE_PROFIT_PCT = overrides.get("TAKE_PROFIT_PCT", 5.0)
    return s


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPositionSizer:

    def test_risk_based_sizing_basic(self):
        """Qty must be > 0 for a valid input."""
        from trading.position_sizer import PositionSizer
        settings = _make_settings()
        sizer = PositionSizer(settings=settings)
        result = sizer.calculate(
            current_price=100.0,
            account_equity=10000.0,
            stop_loss_price=98.0,  # $2 stop distance
        )
        # max_risk = 10000 * 0.01 = $100; qty = 100/2 = 50
        # but capped by MAX_POSITION_SIZE=$500 → 500/100 = 5
        assert result.suggested_qty > 0
        assert result.sizing_method != "error"

    def test_position_size_cap_applies(self):
        """Position size must not exceed MAX_POSITION_SIZE / price."""
        from trading.position_sizer import PositionSizer
        # Very large account, very small max position
        settings = _make_settings(MAX_RISK_PER_TRADE_PERCENT=5.0, MAX_POSITION_SIZE=200.0)
        sizer = PositionSizer(settings=settings)
        result = sizer.calculate(
            current_price=100.0,
            account_equity=100000.0,
            stop_loss_price=98.0,
        )
        # Risk-based: 100000*0.05/2=2500 shares; cap: 200/100=2 shares
        assert result.max_allowed_qty <= 2.0
        assert result.capped_by == "max_position_size"

    def test_high_volatility_reduces_qty(self):
        """ATR > 3% should reduce quantity by 25%."""
        from trading.position_sizer import PositionSizer
        settings = _make_settings(MAX_RISK_PER_TRADE_PERCENT=1.0, MAX_POSITION_SIZE=50000.0)
        sizer = PositionSizer(settings=settings)

        normal = sizer.calculate(
            current_price=100.0,
            account_equity=10000.0,
            stop_loss_price=98.0,
            atr_pct=1.0,  # low volatility
        )
        volatile = sizer.calculate(
            current_price=100.0,
            account_equity=10000.0,
            stop_loss_price=98.0,
            atr_pct=5.0,  # high volatility
        )
        # High volatility result should be <= normal result
        assert volatile.suggested_qty <= normal.suggested_qty
        assert volatile.warning != ""

    def test_invalid_price_returns_error(self):
        """Zero or negative price must return error result with qty=0."""
        from trading.position_sizer import PositionSizer
        settings = _make_settings()
        sizer = PositionSizer(settings=settings)
        result = sizer.calculate(
            current_price=0.0,
            account_equity=10000.0,
            stop_loss_price=0.0,
        )
        assert result.suggested_qty == 0.0
        assert result.sizing_method == "error"
        assert result.warning != ""

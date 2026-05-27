"""
Tests for trading/approval_queue.py

Tests:
  1. Create proposal → PENDING status
  2. Approve → APPROVED, approved_by='user' required
  3. AI cannot approve (ValueError)
  4. Reject → REJECTED
  5. Expired proposal cannot execute
  6. Double-execution blocked
  7. Rejected proposal cannot execute
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Patch DB session to avoid requiring a real SQLite DB."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(
        "trading.approval_queue.get_db_session", lambda: mock_db
    )
    monkeypatch.setattr(
        "db.models.TradeProposal", MagicMock()
    )
    monkeypatch.setattr(
        "db.models.ApprovalEvent", MagicMock()
    )
    monkeypatch.setattr(
        "db.models.AuditLog", MagicMock()
    )
    return mock_db


@pytest.fixture
def queue():
    from trading.approval_queue import ApprovalQueue
    with patch("trading.approval_queue.get_db_session") as mock_db_fn:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db_fn.return_value = mock_db
        q = ApprovalQueue()
    return q


def _make_proposal(queue, ticker="AAPL"):
    with patch("trading.approval_queue.get_db_session") as mock_fn:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_fn.return_value = mock_db
        return queue.create_proposal(
            ticker=ticker,
            side="buy",
            quantity=10.0,
            estimated_price=150.0,
            strategy_name="test_strategy",
            signal_reason="RSI oversold",
            ai_explanation="Technical analysis suggests potential upside.",
            risk_result={"approved": True, "checks_passed": ["kill_switch"], "checks_failed": []},
            broker_mode="mock",
        )


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestProposalCreation:
    def test_create_proposal_returns_pending(self, queue):
        """Newly created proposal must be PENDING."""
        from trading.approval_queue import STATUS_PENDING
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
        assert p.status == STATUS_PENDING

    def test_create_proposal_stores_ticker(self, queue):
        """Ticker must be normalized to uppercase."""
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue, ticker="aapl")
        assert p.ticker == "AAPL"

    def test_create_proposal_has_expiry(self, queue):
        """Proposal must have an expires_at datetime."""
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
        assert p.expires_at is not None
        assert p.expires_at > datetime.now(timezone.utc)


class TestApprovalRules:
    def test_approve_by_user_succeeds(self, queue):
        """User approval must change status to APPROVED."""
        from trading.approval_queue import STATUS_APPROVED
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            approved = queue.approve_proposal(p.proposal_id, approved_by="user")
        assert approved.status == STATUS_APPROVED

    def test_ai_cannot_approve(self, queue):
        """AI approval must raise ValueError."""
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            with pytest.raises(ValueError, match="AI is not permitted"):
                queue.approve_proposal(p.proposal_id, approved_by="ai")

    def test_reject_proposal(self, queue):
        """Rejected proposal must have REJECTED status."""
        from trading.approval_queue import STATUS_REJECTED
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            rejected = queue.reject_proposal(p.proposal_id, reason="Too risky", rejected_by="user")
        assert rejected.status == STATUS_REJECTED

    def test_rejected_proposal_cannot_execute(self, queue):
        """Rejected proposal cannot be executed."""
        from trading.approval_queue import ApprovalQueueError
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            queue.reject_proposal(p.proposal_id, rejected_by="user")
            mock_broker = MagicMock()
            with pytest.raises(ApprovalQueueError, match="rejected"):
                queue.execute_proposal(p.proposal_id, broker=mock_broker)

    def test_double_execution_blocked(self, queue):
        """Executing an already-executed proposal must raise."""
        from trading.approval_queue import ApprovalQueueError, STATUS_EXECUTED
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            queue.approve_proposal(p.proposal_id, approved_by="user")
            mock_broker = MagicMock()
            mock_broker.place_order.return_value = {"id": "order_123", "status": "filled"}
            queue.execute_proposal(p.proposal_id, broker=mock_broker)
            assert p.status == STATUS_EXECUTED
            with pytest.raises(ApprovalQueueError, match="already been executed"):
                queue.execute_proposal(p.proposal_id, broker=mock_broker)

    def test_expired_proposal_cannot_approve(self, queue):
        """An expired proposal cannot be approved."""
        from trading.approval_queue import ApprovalQueueError
        with patch("trading.approval_queue.get_db_session"):
            p = _make_proposal(queue)
            # Force-expire by backdating
            p.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            with pytest.raises(ApprovalQueueError, match="expired"):
                queue.approve_proposal(p.proposal_id, approved_by="user")

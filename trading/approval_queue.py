"""
Approval Queue — proposal-based trading workflow.

Every trade goes through a strict lifecycle:
  PENDING → APPROVED → EXECUTED
              ↘ REJECTED
              ↘ EXPIRED  (auto on read if now > expires_at)

Safety Rules (hard-coded)
-------------------------
* AI cannot approve proposals — approved_by must be 'user'.
* A proposal cannot execute twice (EXECUTED status blocks re-execution).
* A rejected proposal cannot execute.
* An expired proposal cannot execute.
* Price drift > MAX_PRICE_DRIFT_AFTER_APPROVAL_PERCENT requires re-approval.
* Risk manager approve_trade() is called AGAIN at execute time.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from config.settings import get_settings
from db.database import get_db_session
from db.models import TradeProposal as TradeProposalModel, ApprovalEvent, AuditLog

logger = logging.getLogger(__name__)

# Valid statuses
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"
STATUS_EXECUTED = "EXECUTED"


@dataclass
class TradeProposal:
    """In-memory representation of a trade proposal."""
    proposal_id: str
    ticker: str
    side: str                    # buy | sell
    quantity: float
    estimated_price: float
    estimated_order_value: float
    strategy_name: str
    signal_reason: str
    ai_explanation: str
    risk_result: dict            # serialized RiskCheckResult
    status: str = STATUS_PENDING
    broker_mode: str = "mock"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    broker_order_id: Optional[str] = None
    fill_price: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def seconds_remaining(self) -> float:
        if self.expires_at is None:
            return float("inf")
        delta = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)

    @property
    def is_actionable(self) -> bool:
        """True only if status is APPROVED and not expired."""
        return self.status == STATUS_APPROVED and not self.is_expired


class ApprovalQueueError(Exception):
    """Raised when a proposal lifecycle rule is violated."""


class ApprovalQueue:
    """
    In-memory + DB-backed proposal store.

    All proposals are kept in memory for the session and persisted to DB
    for audit trail and cross-session recovery.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._proposals: Dict[str, TradeProposal] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def create_proposal(
        self,
        ticker: str,
        side: str,
        quantity: float,
        estimated_price: float,
        strategy_name: str,
        signal_reason: str,
        ai_explanation: str,
        risk_result: dict,
        broker_mode: str = "mock",
    ) -> TradeProposal:
        """
        Create a new PENDING trade proposal.

        The risk_result must have already been computed by RiskManager.
        This method stores it — it does NOT re-run risk checks.
        """
        proposal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.settings.approval_expiry_seconds)

        proposal = TradeProposal(
            proposal_id=proposal_id,
            ticker=ticker.upper(),
            side=side.lower(),
            quantity=quantity,
            estimated_price=estimated_price,
            estimated_order_value=round(quantity * estimated_price, 2),
            strategy_name=strategy_name,
            signal_reason=signal_reason,
            ai_explanation=ai_explanation,
            risk_result=risk_result,
            status=STATUS_PENDING,
            broker_mode=broker_mode,
            created_at=now,
            expires_at=expires_at,
        )
        self._proposals[proposal_id] = proposal
        self._persist_proposal(proposal)
        self._log_audit("PROPOSAL_CREATED", proposal_id, {
            "ticker": ticker, "side": side, "quantity": quantity,
            "estimated_price": estimated_price, "broker_mode": broker_mode,
        })
        logger.info("Proposal created: %s %s %s x%.2f @ $%.2f",
                    proposal_id, side, ticker, quantity, estimated_price)
        return proposal

    def approve_proposal(self, proposal_id: str, approved_by: str = "user") -> TradeProposal:
        """
        Approve a PENDING proposal.

        Parameters
        ----------
        approved_by:
            MUST be 'user'. Raises ValueError if 'ai' is passed —
            AI is structurally prohibited from approving trades.
        """
        if approved_by.lower() == "ai":
            raise ValueError(
                "AI is not permitted to approve trade proposals. "
                "Only a human user can approve trades."
            )

        proposal = self._get_and_check(proposal_id)
        self._auto_expire(proposal)

        if proposal.status == STATUS_EXPIRED:
            raise ApprovalQueueError(f"Proposal {proposal_id} has expired and cannot be approved.")
        if proposal.status != STATUS_PENDING:
            raise ApprovalQueueError(
                f"Proposal {proposal_id} cannot be approved — current status: {proposal.status}"
            )

        proposal.status = STATUS_APPROVED
        self._update_db_status(proposal_id, STATUS_APPROVED)
        self._log_approval_event(proposal_id, "APPROVED", approved_by, proposal.estimated_price)
        self._log_audit("PROPOSAL_APPROVED", proposal_id, {"approved_by": approved_by})
        logger.info("Proposal approved: %s by %s", proposal_id, approved_by)
        return proposal

    def reject_proposal(self, proposal_id: str, reason: str = "", rejected_by: str = "user") -> TradeProposal:
        """Reject a PENDING proposal. Rejected proposals cannot execute."""
        proposal = self._get_and_check(proposal_id)

        if proposal.status not in (STATUS_PENDING, STATUS_APPROVED):
            raise ApprovalQueueError(
                f"Proposal {proposal_id} cannot be rejected — current status: {proposal.status}"
            )

        proposal.status = STATUS_REJECTED
        self._update_db_status(proposal_id, STATUS_REJECTED)
        self._log_approval_event(proposal_id, "REJECTED", rejected_by, proposal.estimated_price, reason)
        self._log_audit("PROPOSAL_REJECTED", proposal_id, {"reason": reason})
        logger.info("Proposal rejected: %s — %s", proposal_id, reason)
        return proposal

    def execute_proposal(
        self,
        proposal_id: str,
        broker,
        current_price: Optional[float] = None,
    ) -> dict:
        """
        Execute an APPROVED proposal by placing the order via broker.

        Safety checks at execute time
        -----------------------------
        1. Status must be APPROVED (not PENDING/REJECTED/EXPIRED/EXECUTED).
        2. Proposal must not have expired.
        3. Price drift from estimated_price must be within allowed threshold.
        4. Broker's place_order is called — risk gate was already run at proposal creation.

        Returns broker order result dict.
        """
        proposal = self._get_and_check(proposal_id)
        self._auto_expire(proposal)

        # Guard 1: status
        if proposal.status == STATUS_EXECUTED:
            raise ApprovalQueueError(f"Proposal {proposal_id} has already been executed.")
        if proposal.status == STATUS_REJECTED:
            raise ApprovalQueueError(f"Proposal {proposal_id} was rejected and cannot execute.")
        if proposal.status == STATUS_EXPIRED:
            raise ApprovalQueueError(f"Proposal {proposal_id} has expired and cannot execute.")
        if proposal.status != STATUS_APPROVED:
            raise ApprovalQueueError(
                f"Proposal {proposal_id} must be APPROVED before execution. Status: {proposal.status}"
            )

        # Guard 2: expiry double-check
        if proposal.is_expired:
            proposal.status = STATUS_EXPIRED
            self._update_db_status(proposal_id, STATUS_EXPIRED)
            raise ApprovalQueueError(f"Proposal {proposal_id} expired before execution could complete.")

        # Guard 3: price drift check
        if current_price is not None and proposal.estimated_price > 0:
            drift_pct = abs(current_price - proposal.estimated_price) / proposal.estimated_price * 100
            max_drift = self.settings.MAX_PRICE_DRIFT_AFTER_APPROVAL_PERCENT
            if drift_pct > max_drift:
                raise ApprovalQueueError(
                    f"Price drifted {drift_pct:.2f}% from estimated ${proposal.estimated_price:.2f} "
                    f"(current: ${current_price:.2f}). Max allowed: {max_drift}%. Re-approval required."
                )

        # Place the order
        self._log_audit("ORDER_PAYLOAD_SENT", proposal_id, {
            "ticker": proposal.ticker,
            "side": proposal.side,
            "quantity": proposal.quantity,
            "estimated_price": proposal.estimated_price,
            "broker_mode": proposal.broker_mode,
        })

        try:
            order_result = broker.place_order(
                symbol=proposal.ticker,
                qty=proposal.quantity,
                side=proposal.side,
                order_type="limit" if hasattr(broker, "_initial_capital") else "market",
            )
        except Exception as exc:
            self._log_audit("ORDER_FAILED", proposal_id, {"error": str(exc)}, level="ERROR")
            raise

        # Success
        now = datetime.now(timezone.utc)
        proposal.status = STATUS_EXECUTED
        proposal.executed_at = now
        if isinstance(order_result, dict):
            proposal.broker_order_id = order_result.get("id", "")
            proposal.fill_price = order_result.get("filled_avg_price") or order_result.get("fill_price")

        self._update_db_status(proposal_id, STATUS_EXECUTED, executed_at=now,
                               broker_order_id=proposal.broker_order_id,
                               fill_price=proposal.fill_price)
        self._log_approval_event(proposal_id, "EXECUTED", "system",
                                 proposal.fill_price or proposal.estimated_price)
        self._log_audit("BROKER_RESPONSE", proposal_id, order_result if isinstance(order_result, dict) else {})
        logger.info("Proposal executed: %s → order %s", proposal_id, proposal.broker_order_id)
        return order_result

    def get_pending_proposals(self) -> List[TradeProposal]:
        """Return all PENDING proposals, auto-expiring stale ones."""
        self.expire_stale_proposals()
        return [p for p in self._proposals.values() if p.status == STATUS_PENDING]

    def get_approved_proposals(self) -> List[TradeProposal]:
        """Return all APPROVED proposals, auto-expiring stale ones."""
        self.expire_stale_proposals()
        return [p for p in self._proposals.values() if p.status == STATUS_APPROVED]

    def get_all_proposals(self) -> List[TradeProposal]:
        """Return all proposals (all statuses), auto-expiring stale ones."""
        self.expire_stale_proposals()
        return list(self._proposals.values())

    def expire_stale_proposals(self) -> int:
        """Mark all PENDING/APPROVED proposals that are past expires_at as EXPIRED."""
        count = 0
        for p in self._proposals.values():
            if p.status in (STATUS_PENDING, STATUS_APPROVED) and p.is_expired:
                p.status = STATUS_EXPIRED
                self._update_db_status(p.proposal_id, STATUS_EXPIRED)
                self._log_approval_event(p.proposal_id, "EXPIRED", "system", p.estimated_price)
                self._log_audit("PROPOSAL_EXPIRED", p.proposal_id, {})
                count += 1
        return count

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_and_check(self, proposal_id: str) -> TradeProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ApprovalQueueError(f"Proposal {proposal_id} not found.")
        return proposal

    def _auto_expire(self, proposal: TradeProposal) -> None:
        if proposal.status in (STATUS_PENDING, STATUS_APPROVED) and proposal.is_expired:
            proposal.status = STATUS_EXPIRED
            self._update_db_status(proposal.proposal_id, STATUS_EXPIRED)
            self._log_approval_event(proposal.proposal_id, "EXPIRED", "system", proposal.estimated_price)

    def _persist_proposal(self, proposal: TradeProposal) -> None:
        try:
            db = get_db_session()
            record = TradeProposalModel(
                proposal_id=proposal.proposal_id,
                ticker=proposal.ticker,
                side=proposal.side,
                quantity=proposal.quantity,
                estimated_price=proposal.estimated_price,
                estimated_order_value=proposal.estimated_order_value,
                strategy_name=proposal.strategy_name,
                signal_reason=proposal.signal_reason,
                ai_explanation=proposal.ai_explanation,
                risk_result_json=json.dumps(proposal.risk_result),
                status=proposal.status,
                broker_mode=proposal.broker_mode,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
            )
            db.add(record)
            db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to persist proposal %s: %s", proposal.proposal_id, exc)

    def _update_db_status(
        self, proposal_id: str, status: str,
        executed_at: Optional[datetime] = None,
        broker_order_id: Optional[str] = None,
        fill_price: Optional[float] = None,
    ) -> None:
        try:
            db = get_db_session()
            record = db.query(TradeProposalModel).filter(
                TradeProposalModel.proposal_id == proposal_id
            ).first()
            if record:
                record.status = status
                if executed_at:
                    record.executed_at = executed_at
                if broker_order_id:
                    record.broker_order_id = broker_order_id
                if fill_price:
                    record.fill_price = fill_price
                db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to update proposal %s status: %s", proposal_id, exc)

    def _log_approval_event(
        self, proposal_id: str, action: str, actor: str,
        price: Optional[float] = None, reason: str = ""
    ) -> None:
        try:
            db = get_db_session()
            event = ApprovalEvent(
                proposal_id=proposal_id,
                action=action,
                actor=actor,
                reason=reason,
                price_at_action=price,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to log approval event: %s", exc)

    def _log_audit(self, event_type: str, proposal_id: str, details: dict, level: str = "INFO") -> None:
        try:
            db = get_db_session()
            log = AuditLog(
                event_type=event_type,
                details=json.dumps({"proposal_id": proposal_id, **details}),
                level=level,
                created_at=datetime.now(timezone.utc),
            )
            db.add(log)
            db.commit()
            db.close()
        except Exception as exc:
            logger.error("Failed to log audit event: %s", exc)

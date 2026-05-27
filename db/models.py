"""
SQLAlchemy ORM models for the AI Trading Assistant.

Tables
------
signals      — every strategy signal generated
orders       — every order submitted to broker/mock
trade_logs   — closed position P&L records
audit_logs   — full event audit trail (signals, orders, errors, rejects)
risk_events  — detailed record of every risk-check decision
app_settings — persistent key/value app configuration store
"""

from sqlalchemy import (
    Integer, Float, String, Text, Boolean, DateTime,
    ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from db.database import Base


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class Signal(Base):
    """A trading signal produced by a strategy."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)   # BUY/SELL/HOLD
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class Order(Base):
    """Every order request, whether filled, rejected, or cancelled."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)          # buy/sell
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)    # market/limit
    status: Mapped[str] = mapped_column(String(20), nullable=False)        # filled/rejected/cancelled
    broker_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    fill_price: Mapped[float] = mapped_column(Float, nullable=True)
    signal_id: Mapped[int] = mapped_column(Integer, ForeignKey("signals.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=True)           # paper/live/mock
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_orders_ticker_created", "ticker", "created_at"),
    )


# ---------------------------------------------------------------------------
# Trade Logs (closed P&L records)
# ---------------------------------------------------------------------------

class TradeLog(Base):
    """Closed-position record with entry/exit and P&L."""

    __tablename__ = "trade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, nullable=True)
    strategy: Mapped[str] = mapped_column(String(50), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=True)           # paper/live/mock
    status: Mapped[str] = mapped_column(String(20), nullable=False)        # open/closed
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """Full event audit trail — every signal, order, rejection, error."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)              # JSON string
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="INFO")  # INFO/WARNING/ERROR
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Risk Events
# ---------------------------------------------------------------------------

class RiskEvent(Base):
    """Detailed record of every risk-check decision (pass or fail)."""

    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=True, index=True)
    qty: Mapped[float] = mapped_column(Float, nullable=True)
    side: Mapped[str] = mapped_column(String(10), nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checks_passed: Mapped[str] = mapped_column(Text, nullable=True)        # JSON list
    checks_failed: Mapped[str] = mapped_column(Text, nullable=True)        # JSON list
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# App Settings (persistent key-value store)
# ---------------------------------------------------------------------------

class AppSettings(Base):
    """Persistent application settings that can be updated at runtime."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Stock Analysis
# ---------------------------------------------------------------------------

class StockAnalysis(Base):
    """Persisted result of a single-ticker analysis run."""

    __tablename__ = "stock_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    current_price: Mapped[float] = mapped_column(Float, nullable=True)
    signal: Mapped[str] = mapped_column(String(20), nullable=True)         # BUY_CANDIDATE etc
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=True)
    volume_score: Mapped[float] = mapped_column(Float, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float] = mapped_column(Float, nullable=True)
    support_level: Mapped[float] = mapped_column(Float, nullable=True)
    resistance_level: Mapped[float] = mapped_column(Float, nullable=True)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=True)
    indicators_json: Mapped[str] = mapped_column(Text, nullable=True)       # JSON
    timeframe_bias: Mapped[str] = mapped_column(String(20), nullable=True)  # short_term/swing/long_term
    portfolio_note: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Stock Rankings
# ---------------------------------------------------------------------------

class StockRanking(Base):
    """A single ranking session result (ordered list of tickers)."""

    __tablename__ = "stock_rankings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # UUID
    tickers_input: Mapped[str] = mapped_column(Text, nullable=True)        # comma-sep input
    ranked_results_json: Mapped[str] = mapped_column(Text, nullable=True)  # full JSON
    top_ticker: Mapped[str] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Trade Proposals
# ---------------------------------------------------------------------------

class TradeProposal(Base):
    """Full lifecycle record of a proposed trade awaiting user approval."""

    __tablename__ = "trade_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)  # UUID
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)           # buy/sell
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_price: Mapped[float] = mapped_column(Float, nullable=True)
    estimated_order_value: Mapped[float] = mapped_column(Float, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=True)
    signal_reason: Mapped[str] = mapped_column(Text, nullable=True)
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=True)
    risk_result_json: Mapped[str] = mapped_column(Text, nullable=True)      # JSON of RiskCheckResult
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    # PENDING | APPROVED | REJECTED | EXPIRED | EXECUTED
    broker_mode: Mapped[str] = mapped_column(String(20), nullable=True)     # paper/live/mock
    broker_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    fill_price: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Approval Events
# ---------------------------------------------------------------------------

class ApprovalEvent(Base):
    """Immutable log of every approve/reject/expire action on a trade proposal."""

    __tablename__ = "approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)         # APPROVED/REJECTED/EXPIRED/EXECUTED
    actor: Mapped[str] = mapped_column(String(50), nullable=True)           # 'user' always (AI cannot approve)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    price_at_action: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Broker Connections
# ---------------------------------------------------------------------------

class BrokerConnection(Base):
    """Records which broker was active and when it was switched."""

    __tablename__ = "broker_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_type: Mapped[str] = mapped_column(String(50), nullable=False)    # mock/alpaca_paper/alpaca_live/robinhood_watchlist
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[str] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------

class Watchlist(Base):
    """User-saved ticker groups (Robinhood manual, custom, default)."""

    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=True)          # manual/robinhood_csv/custom
    tickers_json: Mapped[str] = mapped_column(Text, nullable=True)          # JSON list of tickers
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Holdings Snapshot
# ---------------------------------------------------------------------------

class HoldingsSnapshot(Base):
    """Periodic snapshot of positions for portfolio-aware analysis."""

    __tablename__ = "holdings_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=True)          # broker type
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=True)         # JSON list of positions
    total_value: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

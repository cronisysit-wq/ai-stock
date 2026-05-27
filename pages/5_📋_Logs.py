"""
Logs Page — Risk Events · Audit Trail · Signal History · Order History
Complete audit trail with per-tab filters, color coding, and CSV export.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import json, io

st.set_page_config(
    page_title="Logs & Audit Trail | AI Trading Assistant",
    page_icon="📋",
    layout="wide",
)

# ── Premium CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
:root{
    --accent-gold:#D4AF37;--profit-green:#00C853;--loss-red:#FF1744;
    --glass-bg:rgba(26,26,46,0.72);--glass-border:rgba(212,175,55,0.12);
    --bg-dark:#0d0d1a;--cyan:#00BCD4;--orange:#FFA726;
}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.section-header{font-size:1.05rem;font-weight:700;color:#D4AF37;text-transform:uppercase;
    letter-spacing:1.5px;padding-bottom:0.5rem;margin-bottom:1rem;
    border-bottom:1px solid rgba(212,175,55,0.18);}
.gold-divider{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);
    margin:1.2rem 0;border:none;}
.metric-card{background:var(--glass-bg);backdrop-filter:blur(16px);
    border:1px solid var(--glass-border);border-radius:14px;padding:1rem 1.2rem;
    position:relative;overflow:hidden;}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,#D4AF37,transparent);}
.metric-label{font-size:0.72rem;font-weight:700;text-transform:uppercase;
    letter-spacing:1.2px;color:#888;margin-bottom:0.2rem;}
.metric-value{font-size:1.5rem;font-weight:800;color:#fff;
    font-family:'JetBrains Mono',monospace;}
.badge{display:inline-block;padding:2px 10px;border-radius:6px;font-weight:700;
    font-size:0.78rem;letter-spacing:0.5px;font-family:'JetBrains Mono',monospace;}
.badge-buy{background:rgba(0,200,83,0.15);color:#00C853;border:1px solid rgba(0,200,83,0.25);}
.badge-sell{background:rgba(255,23,68,0.15);color:#FF1744;border:1px solid rgba(255,23,68,0.25);}
.badge-hold{background:rgba(212,175,55,0.15);color:#D4AF37;border:1px solid rgba(212,175,55,0.25);}
.badge-approved{background:rgba(0,200,83,0.15);color:#00C853;border:1px solid rgba(0,200,83,0.3);}
.badge-rejected{background:rgba(255,23,68,0.15);color:#FF1744;border:1px solid rgba(255,23,68,0.3);}
.empty-state{text-align:center;padding:3rem 1rem;color:#666;font-size:0.95rem;}
.empty-state .icon{font-size:2.5rem;margin-bottom:0.8rem;}
.stTabs [data-baseweb="tab-list"]{gap:6px;}
.stTabs [data-baseweb="tab"]{
    background:rgba(26,26,46,0.5);border:1px solid rgba(212,175,55,0.1);
    border-radius:8px 8px 0 0;padding:8px 18px;color:#aaa;font-weight:600;}
.stTabs [aria-selected="true"]{
    background:rgba(212,175,55,0.12)!important;
    border-bottom:2px solid #D4AF37!important;color:#D4AF37!important;}
</style>
""", unsafe_allow_html=True)

# ── Module imports ────────────────────────────────────────────────────────────
try:
    from db.database import init_db, get_db_session
    from db.models import AuditLog, Signal, Order, RiskEvent, TradeProposal, ApprovalEvent, StockRanking, TradeProposal, ApprovalEvent, StockRanking
    init_db()
    DB_OK = True
except Exception:
    DB_OK = False

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='margin-bottom:1.5rem;'>
  <h1 style='margin:0;font-size:2rem;font-weight:900;
      background:linear-gradient(135deg,#D4AF37,#F5E6A3);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
      📋 Logs & Audit Trail
  </h1>
  <p style='margin:0;color:#888;font-size:0.9rem;'>
      Risk events · Audit log · Signal history · Order history — full traceability
  </p>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA LOADERS
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_json(raw, max_len=200):
    """Parse JSON string safely, return truncated string."""
    try:
        obj = json.loads(raw) if raw else {}
        return json.dumps(obj, indent=None)[:max_len]
    except Exception:
        return str(raw)[:max_len] if raw else ""


def _parse_json_list(raw):
    """Parse a JSON list string, return Python list."""
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


# ── Risk Events ───────────────────────────────────────────────────────────────
def load_risk_events(approved_filter="ALL", symbol_filter="", date_from=None, date_to=None, limit=500):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(RiskEvent).order_by(RiskEvent.created_at.desc())
        if approved_filter == "APPROVED":
            query = query.filter(RiskEvent.approved == True)
        elif approved_filter == "REJECTED":
            query = query.filter(RiskEvent.approved == False)
        if symbol_filter:
            query = query.filter(RiskEvent.symbol == symbol_filter.upper())
        if date_from:
            query = query.filter(RiskEvent.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.filter(RiskEvent.created_at <= datetime.combine(date_to, datetime.max.time()))
        events = query.limit(limit).all()
        for e in events:
            passed = _parse_json_list(e.checks_passed)
            failed = _parse_json_list(e.checks_failed)
            rows.append({
                "Timestamp": str(e.created_at)[:19],
                "Symbol": e.symbol or "—",
                "Qty": e.qty if e.qty else "—",
                "Side": (e.side or "").upper(),
                "Price": f"${e.price:,.2f}" if e.price else "—",
                "Approved": "✅" if e.approved else "❌",
                "Passed": len(passed),
                "Failed": ", ".join(failed) if failed else "—",
                "Rejection": (e.rejection_reason or "—")[:120],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Audit Logs ────────────────────────────────────────────────────────────────
def load_audit_logs(level_filter="ALL", event_filter="ALL", date_from=None, date_to=None, limit=500):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
        if level_filter != "ALL":
            query = query.filter(AuditLog.level == level_filter)
        if event_filter != "ALL":
            query = query.filter(AuditLog.event_type == event_filter)
        if date_from:
            query = query.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
        logs = query.limit(limit).all()
        for log in logs:
            rows.append({
                "ID": log.id,
                "Timestamp": str(log.created_at)[:19],
                "Level": log.level or "INFO",
                "Event Type": log.event_type or "",
                "Details": _safe_json(log.details),
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Signals ───────────────────────────────────────────────────────────────────
def load_signals_log(ticker_filter="", strategy_filter="", signal_type_filter="ALL", limit=500):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(Signal).order_by(Signal.created_at.desc())
        if ticker_filter:
            query = query.filter(Signal.ticker == ticker_filter.upper())
        if strategy_filter:
            query = query.filter(Signal.strategy == strategy_filter)
        if signal_type_filter != "ALL":
            query = query.filter(Signal.signal_type == signal_type_filter)
        sigs = query.limit(limit).all()
        for s in sigs:
            sig = s.signal_type or "HOLD"
            badge_cls = {"BUY": "badge-buy", "SELL": "badge-sell"}.get(sig, "badge-hold")
            rows.append({
                "Timestamp": str(s.created_at)[:19],
                "Ticker": s.ticker,
                "Strategy": s.strategy,
                "Signal": sig,
                "_signal_badge": f"<span class='badge {badge_cls}'>{sig}</span>",
                "Confidence": f"{s.confidence:.1%}" if s.confidence else "—",
                "Explanation": (s.explanation or "")[:140],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Orders ────────────────────────────────────────────────────────────────────
def load_orders_log(status_filter="ALL", mode_filter="ALL", ticker_filter="", limit=500):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(Order).order_by(Order.created_at.desc())
        if status_filter != "ALL":
            query = query.filter(Order.status == status_filter.lower())
        if mode_filter != "ALL":
            query = query.filter(Order.mode == mode_filter.lower())
        if ticker_filter:
            query = query.filter(Order.ticker == ticker_filter.upper())
        ords = query.limit(limit).all()
        for o in ords:
            rows.append({
                "Timestamp": str(o.created_at)[:19],
                "Ticker": o.ticker,
                "Side": (o.side or "").upper(),
                "Qty": o.qty,
                "Type": o.order_type,
                "Status": o.status,
                "Fill Price": f"${o.fill_price:,.2f}" if o.fill_price else "—",
                "Mode": o.mode or "—",
                "Broker ID": str(o.broker_order_id or "")[:20],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Trade Proposals ───────────────────────────────────────────────────────────
def load_trade_proposals(status_filter="ALL", ticker_filter="", limit=200):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(TradeProposal).order_by(TradeProposal.created_at.desc())
        if status_filter != "ALL":
            query = query.filter(TradeProposal.status == status_filter)
        if ticker_filter:
            query = query.filter(TradeProposal.ticker == ticker_filter.upper())
        for p in query.limit(limit).all():
            rows.append({
                "Created": str(p.created_at)[:19],
                "ID": str(p.proposal_id or "")[:16] + "...",
                "Ticker": p.ticker or "—",
                "Side": (p.side or "").upper(),
                "Qty": p.quantity,
                "Est. Price": f"${p.estimated_price:,.2f}" if p.estimated_price else "—",
                "Est. Value": f"${p.estimated_order_value:,.2f}" if p.estimated_order_value else "—",
                "Status": p.status or "—",
                "Mode": p.broker_mode or "—",
                "Strategy": p.strategy_name or "—",
                "Expires": str(p.expires_at)[:19] if p.expires_at else "—",
                "Executed": str(p.executed_at)[:19] if p.executed_at else "—",
                "Fill Price": f"${p.fill_price:,.2f}" if p.fill_price else "—",
                "Broker ID": str(p.broker_order_id or "")[:20],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Approval Events ───────────────────────────────────────────────────────────
def load_approval_events(action_filter="ALL", limit=200):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(ApprovalEvent).order_by(ApprovalEvent.created_at.desc())
        if action_filter != "ALL":
            query = query.filter(ApprovalEvent.action == action_filter)
        for e in query.limit(limit).all():
            rows.append({
                "Timestamp": str(e.created_at)[:19],
                "Proposal ID": str(e.proposal_id or "")[:16] + "...",
                "Action": e.action or "—",
                "Actor": e.actor or "—",
                "Price at Action": f"${e.price_at_action:,.2f}" if e.price_at_action else "—",
                "Reason": (e.reason or "")[:100],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Stock Rankings ────────────────────────────────────────────────────────────
def load_stock_rankings(limit=50):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        for r in db.query(StockRanking).order_by(StockRanking.created_at.desc()).limit(limit).all():
            rows.append({
                "Timestamp": str(r.created_at)[:19],
                "Session ID": str(r.session_id or "")[:12] + "...",
                "Top Ticker": r.top_ticker or "—",
                "Tickers Analyzed": r.tickers_input or "—",
                "Results (JSON)": (r.ranked_results_json or "")[:120],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Trade Proposals ───────────────────────────────────────────────────────────
def load_trade_proposals(status_filter="ALL", ticker_filter="", limit=200):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(TradeProposal).order_by(TradeProposal.created_at.desc())
        if status_filter != "ALL":
            query = query.filter(TradeProposal.status == status_filter)
        if ticker_filter:
            query = query.filter(TradeProposal.ticker == ticker_filter.upper())
        for p in query.limit(limit).all():
            rows.append({
                "Created": str(p.created_at)[:19],
                "ID": str(p.proposal_id or "")[:16] + "...",
                "Ticker": p.ticker or "—",
                "Side": (p.side or "").upper(),
                "Qty": p.quantity,
                "Est. Price": f"${p.estimated_price:,.2f}" if p.estimated_price else "—",
                "Est. Value": f"${p.estimated_order_value:,.2f}" if p.estimated_order_value else "—",
                "Status": p.status or "—",
                "Mode": p.broker_mode or "—",
                "Strategy": p.strategy_name or "—",
                "Expires": str(p.expires_at)[:19] if p.expires_at else "—",
                "Executed": str(p.executed_at)[:19] if p.executed_at else "—",
                "Fill Price": f"${p.fill_price:,.2f}" if p.fill_price else "—",
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Approval Events ───────────────────────────────────────────────────────────
def load_approval_events(action_filter="ALL", limit=200):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        query = db.query(ApprovalEvent).order_by(ApprovalEvent.created_at.desc())
        if action_filter != "ALL":
            query = query.filter(ApprovalEvent.action == action_filter)
        for e in query.limit(limit).all():
            rows.append({
                "Timestamp": str(e.created_at)[:19],
                "Proposal ID": str(e.proposal_id or "")[:16] + "...",
                "Action": e.action or "—",
                "Actor": e.actor or "—",
                "Price": f"${e.price_at_action:,.2f}" if e.price_at_action else "—",
                "Reason": (e.reason or "")[:100],
            })
        db.close()
    except Exception:
        pass
    return rows


# ── Stock Rankings ────────────────────────────────────────────────────────────
def load_stock_rankings(limit=50):
    rows = []
    if not DB_OK:
        return rows
    try:
        db = get_db_session()
        for r in db.query(StockRanking).order_by(StockRanking.created_at.desc()).limit(limit).all():
            rows.append({
                "Timestamp": str(r.created_at)[:19],
                "Session": str(r.session_id or "")[:12] + "...",
                "Top Ticker": r.top_ticker or "—",
                "Tickers Input": (r.tickers_input or "")[:80],
                "Results Summary": (r.ranked_results_json or "")[:120],
            })
        db.close()
    except Exception:
        pass
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO / FALLBACK DATA
# ═══════════════════════════════════════════════════════════════════════════════

def demo_risk_events():
    now = datetime.now()
    return [
        {"Timestamp": str(now - timedelta(minutes=12))[:19], "Symbol": "AAPL", "Qty": 15,
         "Side": "BUY", "Price": "$189.42", "Approved": "✅", "Passed": 12,
         "Failed": "—", "Rejection": "—"},
        {"Timestamp": str(now - timedelta(minutes=8))[:19], "Symbol": "TSLA", "Qty": 50,
         "Side": "BUY", "Price": "$245.30", "Approved": "❌", "Passed": 10,
         "Failed": "max_position_size, daily_loss_limit",
         "Rejection": "Position value $12,265 exceeds max $10,000"},
        {"Timestamp": str(now - timedelta(minutes=5))[:19], "Symbol": "MSFT", "Qty": 8,
         "Side": "SELL", "Price": "$428.75", "Approved": "✅", "Passed": 12,
         "Failed": "—", "Rejection": "—"},
        {"Timestamp": str(now - timedelta(minutes=2))[:19], "Symbol": "NVDA", "Qty": 100,
         "Side": "BUY", "Price": "$950.10", "Approved": "❌", "Passed": 7,
         "Failed": "max_portfolio_exposure, concentrated_position, max_order_value",
         "Rejection": "Order value $95,010 exceeds daily limit"},
        {"Timestamp": str(now - timedelta(minutes=1))[:19], "Symbol": "GOOGL", "Qty": 5,
         "Side": "BUY", "Price": "$176.50", "Approved": "✅", "Passed": 12,
         "Failed": "—", "Rejection": "—"},
    ]


def demo_audit_logs():
    now = datetime.now()
    return [
        {"ID": 1, "Timestamp": str(now - timedelta(minutes=10))[:19], "Level": "INFO",
         "Event Type": "ORDER_SUBMITTED", "Details": '{"symbol":"AAPL","qty":10,"side":"buy"}'},
        {"ID": 2, "Timestamp": str(now - timedelta(minutes=9))[:19], "Level": "INFO",
         "Event Type": "ORDER_ACCEPTED", "Details": '{"id":"abc123","status":"filled"}'},
        {"ID": 3, "Timestamp": str(now - timedelta(minutes=7))[:19], "Level": "WARNING",
         "Event Type": "RISK_CHECK_FAILED", "Details": '{"reason":"Position size exceeds limit"}'},
        {"ID": 4, "Timestamp": str(now - timedelta(minutes=5))[:19], "Level": "INFO",
         "Event Type": "SIGNAL_GENERATED", "Details": '{"ticker":"MSFT","signal":"BUY","confidence":0.72}'},
        {"ID": 5, "Timestamp": str(now - timedelta(minutes=3))[:19], "Level": "ERROR",
         "Event Type": "ORDER_ERROR", "Details": '{"error":"Insufficient buying power"}'},
        {"ID": 6, "Timestamp": str(now - timedelta(minutes=2))[:19], "Level": "WARNING",
         "Event Type": "KILL_SWITCH_ENGAGED", "Details": '{"message":"Emergency stop activated"}'},
        {"ID": 7, "Timestamp": str(now - timedelta(minutes=15))[:19], "Level": "INFO",
         "Event Type": "RISK_CHECK_PASSED", "Details": '{"checks":12,"symbol":"AAPL"}'},
        {"ID": 8, "Timestamp": str(now - timedelta(minutes=12))[:19], "Level": "INFO",
         "Event Type": "ACCOUNT_INFO", "Details": '{"equity":100000,"buying_power":50000}'},
    ]


def demo_signals():
    now = datetime.now()
    return [
        {"Timestamp": str(now - timedelta(minutes=20))[:19], "Ticker": "AAPL", "Strategy": "RSI_MACD",
         "Signal": "BUY", "_signal_badge": "<span class='badge badge-buy'>BUY</span>",
         "Confidence": "78.5%", "Explanation": "RSI oversold at 28, MACD bullish crossover confirmed"},
        {"Timestamp": str(now - timedelta(minutes=15))[:19], "Ticker": "TSLA", "Strategy": "ML_Ensemble",
         "Signal": "SELL", "_signal_badge": "<span class='badge badge-sell'>SELL</span>",
         "Confidence": "65.2%", "Explanation": "Price below 50-day SMA, volume declining"},
        {"Timestamp": str(now - timedelta(minutes=10))[:19], "Ticker": "MSFT", "Strategy": "RSI_MACD",
         "Signal": "HOLD", "_signal_badge": "<span class='badge badge-hold'>HOLD</span>",
         "Confidence": "52.0%", "Explanation": "Mixed signals — RSI neutral, MACD flat"},
        {"Timestamp": str(now - timedelta(minutes=5))[:19], "Ticker": "NVDA", "Strategy": "Momentum",
         "Signal": "BUY", "_signal_badge": "<span class='badge badge-buy'>BUY</span>",
         "Confidence": "88.1%", "Explanation": "Strong breakout above resistance with high volume"},
    ]


def demo_orders():
    now = datetime.now()
    return [
        {"Timestamp": str(now - timedelta(minutes=18))[:19], "Ticker": "AAPL", "Side": "BUY",
         "Qty": 10, "Type": "market", "Status": "filled", "Fill Price": "$189.42",
         "Mode": "paper", "Broker ID": "mock_abc123"},
        {"Timestamp": str(now - timedelta(minutes=12))[:19], "Ticker": "MSFT", "Side": "SELL",
         "Qty": 5, "Type": "market", "Status": "filled", "Fill Price": "$428.75",
         "Mode": "paper", "Broker ID": "mock_def456"},
        {"Timestamp": str(now - timedelta(minutes=6))[:19], "Ticker": "TSLA", "Side": "BUY",
         "Qty": 50, "Type": "market", "Status": "rejected", "Fill Price": "—",
         "Mode": "paper", "Broker ID": "—"},
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER — empty state
# ═══════════════════════════════════════════════════════════════════════════════

def _empty_state(icon: str, msg: str):
    st.markdown(f"""
    <div class='empty-state'>
        <div class='icon'>{icon}</div>
        <div>{msg}</div>
    </div>
    """, unsafe_allow_html=True)


def _csv_download(df: pd.DataFrame, prefix: str, key: str):
    """Render a CSV download button for the given DataFrame."""
    csv_buf = df.to_csv(index=False)
    st.download_button(
        "⬇️  Download as CSV",
        data=csv_buf,
        file_name=f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key=key,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GLOBAL CONTROLS
# ═══════════════════════════════════════════════════════════════════════════════

gc1, gc2 = st.columns([3, 1])
with gc2:
    auto_refresh = st.checkbox("🔄 Auto-Refresh (10 s)", value=False)

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════════════════════════

tab_risk, tab_audit, tab_signals, tab_orders, tab_proposals, tab_approvals, tab_rankings = st.tabs([
    "🛡️ Risk Events", "📋 Audit Log", "🎯 Signal History", "📦 Order History",
    "📝 Trade Proposals", "✅ Approval Events", "📊 Stock Rankings",
])


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — RISK EVENTS
# ─────────────────────────────────────────────────────────────────────────────
with tab_risk:
    st.markdown("<div class='section-header'>🔍 Risk Event Filters</div>", unsafe_allow_html=True)
    rf1, rf2, rf3, rf4 = st.columns([1, 1, 1, 1])
    with rf1:
        re_approved = st.selectbox("Status", ["ALL", "APPROVED", "REJECTED"], key="re_appr")
    with rf2:
        re_symbol = st.text_input("Symbol", value="", placeholder="e.g. AAPL", key="re_sym")
    with rf3:
        re_date_from = st.date_input("From Date", value=date.today() - timedelta(days=30), key="re_df")
    with rf4:
        re_date_to = st.date_input("To Date", value=date.today(), key="re_dt")

    risk_rows = load_risk_events(re_approved, re_symbol, re_date_from, re_date_to)

    is_demo = False
    if not risk_rows:
        risk_rows = demo_risk_events()
        is_demo = True
        st.info("📊 Showing demo risk events. Execute trades to populate real data.")

    # Stats
    total_re = len(risk_rows)
    approved_ct = sum(1 for r in risk_rows if r["Approved"] == "✅")
    rejected_ct = total_re - approved_ct

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Events</div>"
                    f"<div class='metric-value'>{total_re}</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Approved</div>"
                    f"<div class='metric-value' style='color:#00C853;'>{approved_ct}</div></div>",
                    unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Rejected</div>"
                    f"<div class='metric-value' style='color:#FF1744;'>{rejected_ct}</div></div>",
                    unsafe_allow_html=True)
    with s4:
        rate = (approved_ct / total_re * 100) if total_re else 0
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Pass Rate</div>"
                    f"<div class='metric-value' style='color:#D4AF37;'>{rate:.0f}%</div></div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    risk_df = pd.DataFrame(risk_rows)

    def _color_risk_row(row):
        if row["Approved"] == "✅":
            return ["background:rgba(0,200,83,0.07);"] * len(row)
        return ["background:rgba(255,23,68,0.07);"] * len(row)

    styled_risk = risk_df.style.apply(_color_risk_row, axis=1)
    st.dataframe(styled_risk, use_container_width=True, hide_index=True, height=420)

    _csv_download(risk_df, "risk_events", "csv_risk")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — AUDIT LOG (enhanced)
# ─────────────────────────────────────────────────────────────────────────────
with tab_audit:
    st.markdown("<div class='section-header'>🔍 Audit Log Filters</div>", unsafe_allow_html=True)
    af1, af2, af3, af4 = st.columns([1, 1.5, 1, 1])
    with af1:
        al_level = st.selectbox("Level", ["ALL", "INFO", "WARNING", "ERROR"], key="al_lvl")
    with af2:
        event_types_list = [
            "ALL", "ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_ERROR",
            "ORDER_BLOCKED", "ORDER_CANCELLED", "RISK_CHECK_PASSED",
            "RISK_CHECK_FAILED", "KILL_SWITCH_ENGAGED", "KILL_SWITCH_DISENGAGED",
            "SIGNAL_GENERATED", "ACCOUNT_ERROR", "POSITIONS_ERROR",
        ]
        al_event = st.selectbox("Event Type", event_types_list, key="al_evt")
    with af3:
        al_date_from = st.date_input("From Date", value=date.today() - timedelta(days=30), key="al_df")
    with af4:
        al_date_to = st.date_input("To Date", value=date.today(), key="al_dt")

    audit_rows = load_audit_logs(al_level, al_event, al_date_from, al_date_to)

    is_demo_audit = False
    if not audit_rows:
        audit_rows = demo_audit_logs()
        is_demo_audit = True
        st.info("📊 Showing demo audit logs. Run trades to populate real audit data.")

    # Stats
    total_al = len(audit_rows)
    info_ct = sum(1 for r in audit_rows if r["Level"] == "INFO")
    warn_ct = sum(1 for r in audit_rows if r["Level"] == "WARNING")
    err_ct  = sum(1 for r in audit_rows if r["Level"] == "ERROR")

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Events</div>"
                    f"<div class='metric-value'>{total_al}</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Info</div>"
                    f"<div class='metric-value' style='color:#00BCD4;'>{info_ct}</div></div>",
                    unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Warnings</div>"
                    f"<div class='metric-value' style='color:#FFA726;'>{warn_ct}</div></div>",
                    unsafe_allow_html=True)
    with s4:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Errors</div>"
                    f"<div class='metric-value' style='color:#FF1744;'>{err_ct}</div></div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    audit_df = pd.DataFrame(audit_rows)

    def _color_level(val):
        if val == "ERROR":
            return "color:#FF1744;font-weight:700;"
        if val == "WARNING":
            return "color:#FFA726;font-weight:700;"
        return "color:#00BCD4;font-weight:600;"

    def _color_event(val):
        v = str(val)
        if "ERROR" in v or "FAILED" in v or "BLOCKED" in v:
            return "color:#FF1744;"
        if "WARNING" in v or "KILL" in v:
            return "color:#FFA726;"
        return "color:#E0E0E0;"

    def _color_audit_row(row):
        lvl = row["Level"]
        if lvl == "ERROR":
            return ["background:rgba(255,23,68,0.06);"] * len(row)
        if lvl == "WARNING":
            return ["background:rgba(255,167,38,0.06);"] * len(row)
        return [""] * len(row)

    styled_audit = (
        audit_df.style
        .apply(_color_audit_row, axis=1)
        .map(_color_level, subset=["Level"])
        .map(_color_event, subset=["Event Type"])
    )
    st.dataframe(styled_audit, use_container_width=True, hide_index=True, height=420)

    _csv_download(audit_df, "audit_log", "csv_audit")

    # ── Event Type Distribution Chart ─────────────────────────────────
    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>📊 Event Type Distribution</div>", unsafe_allow_html=True)

    event_counts = audit_df.groupby("Event Type").size().reset_index(name="Count")
    event_counts = event_counts.sort_values("Count", ascending=True)

    bar_colors = []
    for evt in event_counts["Event Type"]:
        if "ERROR" in evt or "FAILED" in evt or "BLOCKED" in evt:
            bar_colors.append("#FF1744")
        elif "WARNING" in evt or "KILL" in evt:
            bar_colors.append("#FFA726")
        else:
            bar_colors.append("#00BCD4")

    fig_evt = go.Figure(go.Bar(
        x=event_counts["Count"],
        y=event_counts["Event Type"],
        orientation="h",
        marker=dict(color=bar_colors, line=dict(color="rgba(255,255,255,0.08)", width=0.5)),
        text=event_counts["Count"],
        textposition="auto",
        textfont=dict(family="JetBrains Mono", size=11, color="#fff"),
    ))
    fig_evt.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,26,46,0.5)",
        height=max(220, len(event_counts) * 38),
        margin=dict(l=0, r=20, t=10, b=0),
        xaxis=dict(title="Count", gridcolor="rgba(255,255,255,0.04)",
                   title_font=dict(color="#888", size=11)),
        yaxis=dict(gridcolor="rgba(255,255,255,0.04)",
                   tickfont=dict(family="JetBrains Mono", size=11)),
    )
    st.plotly_chart(fig_evt, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — SIGNAL HISTORY
# ─────────────────────────────────────────────────────────────────────────────
with tab_signals:
    st.markdown("<div class='section-header'>🔍 Signal Filters</div>", unsafe_allow_html=True)
    sf1, sf2, sf3 = st.columns([1, 1, 1])
    with sf1:
        sig_ticker = st.text_input("Ticker", value="", placeholder="e.g. AAPL", key="sig_tk")
    with sf2:
        sig_strategy = st.text_input("Strategy", value="", placeholder="e.g. RSI_MACD", key="sig_st")
    with sf3:
        sig_type = st.selectbox("Signal Type", ["ALL", "BUY", "SELL", "HOLD"], key="sig_tp")

    signal_rows = load_signals_log(sig_ticker, sig_strategy, sig_type)

    is_demo_sig = False
    if not signal_rows:
        signal_rows = demo_signals()
        is_demo_sig = True
        st.info("📊 Showing demo signals. Generate signals from Strategy page to see real data.")

    # Stats
    total_sig = len(signal_rows)
    buy_ct = sum(1 for r in signal_rows if r["Signal"] == "BUY")
    sell_ct = sum(1 for r in signal_rows if r["Signal"] == "SELL")
    hold_ct = sum(1 for r in signal_rows if r["Signal"] == "HOLD")

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Signals</div>"
                    f"<div class='metric-value'>{total_sig}</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Buy</div>"
                    f"<div class='metric-value' style='color:#00C853;'>{buy_ct}</div></div>",
                    unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Sell</div>"
                    f"<div class='metric-value' style='color:#FF1744;'>{sell_ct}</div></div>",
                    unsafe_allow_html=True)
    with s4:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Hold</div>"
                    f"<div class='metric-value' style='color:#D4AF37;'>{hold_ct}</div></div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    sig_df = pd.DataFrame(signal_rows)
    # Display without the raw badge HTML column
    display_sig_df = sig_df.drop(columns=["_signal_badge"], errors="ignore")

    def _color_signal(val):
        if val == "BUY":
            return "color:#00C853;font-weight:700;"
        if val == "SELL":
            return "color:#FF1744;font-weight:700;"
        return "color:#D4AF37;font-weight:700;"

    styled_sig = display_sig_df.style.map(_color_signal, subset=["Signal"])
    st.dataframe(styled_sig, use_container_width=True, hide_index=True, height=420)

    _csv_download(display_sig_df, "signal_history", "csv_sig")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 4 — ORDER HISTORY
# ─────────────────────────────────────────────────────────────────────────────
with tab_orders:
    st.markdown("<div class='section-header'>🔍 Order Filters</div>", unsafe_allow_html=True)
    of1, of2, of3 = st.columns([1, 1, 1])
    with of1:
        ord_status = st.selectbox("Status", ["ALL", "FILLED", "REJECTED", "CANCELLED", "PENDING"], key="ord_st")
    with of2:
        ord_mode = st.selectbox("Mode", ["ALL", "PAPER", "LIVE", "MOCK"], key="ord_md")
    with of3:
        ord_ticker = st.text_input("Ticker", value="", placeholder="e.g. AAPL", key="ord_tk")

    order_rows = load_orders_log(ord_status, ord_mode, ord_ticker)

    is_demo_ord = False
    if not order_rows:
        order_rows = demo_orders()
        is_demo_ord = True
        st.info("📊 Showing demo orders. Place trades to populate real order data.")

    # Stats
    total_ord = len(order_rows)
    filled_ct = sum(1 for r in order_rows if "fill" in str(r["Status"]).lower())
    rejected_ord = sum(1 for r in order_rows if "reject" in str(r["Status"]).lower())
    other_ord = total_ord - filled_ct - rejected_ord

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Total Orders</div>"
                    f"<div class='metric-value'>{total_ord}</div></div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Filled</div>"
                    f"<div class='metric-value' style='color:#00C853;'>{filled_ct}</div></div>",
                    unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Rejected</div>"
                    f"<div class='metric-value' style='color:#FF1744;'>{rejected_ord}</div></div>",
                    unsafe_allow_html=True)
    with s4:
        st.markdown(f"<div class='metric-card'><div class='metric-label'>Other</div>"
                    f"<div class='metric-value' style='color:#D4AF37;'>{other_ord}</div></div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    ord_df = pd.DataFrame(order_rows)

    def _color_side(val):
        if val == "BUY":
            return "color:#00C853;font-weight:700;"
        if val == "SELL":
            return "color:#FF1744;font-weight:700;"
        return ""

    def _color_status(val):
        v = str(val).lower()
        if "fill" in v:
            return "color:#00C853;"
        if "cancel" in v or "error" in v or "reject" in v:
            return "color:#FF1744;"
        return "color:#D4AF37;"

    styled_ord = (
        ord_df.style
        .map(_color_side, subset=["Side"])
        .map(_color_status, subset=["Status"])
    )
    st.dataframe(styled_ord, use_container_width=True, hide_index=True, height=420)

    _csv_download(ord_df, "order_history", "csv_ord")


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO REFRESH
# ═══════════════════════════════════════════════════════════════════════════════
if auto_refresh:
    import time
    time.sleep(10)
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
#  TAB 5 — TRADE PROPOSALS
# ─────────────────────────────────────────────────────────────────────────────
with tab_proposals:
    st.markdown("<div class='section-header'>🔍 Trade Proposal Filters</div>", unsafe_allow_html=True)
    pf1, pf2 = st.columns([1, 1])
    with pf1:
        prop_status = st.selectbox("Status", ["ALL", "PENDING", "APPROVED", "EXECUTED", "REJECTED", "EXPIRED"], key="prop_status_filter")
    with pf2:
        prop_ticker = st.text_input("Ticker", value="", placeholder="e.g. AAPL", key="prop_ticker_filter")

    proposal_rows = load_trade_proposals(prop_status, prop_ticker)

    if not proposal_rows:
        st.info("📊 No trade proposals yet. Use **Strategy Signals** or **Trading Modes** to create proposals.")
    else:
        p_total = len(proposal_rows)
        p_pending = sum(1 for r in proposal_rows if r["Status"] == "PENDING")
        p_executed = sum(1 for r in proposal_rows if r["Status"] == "EXECUTED")
        p_rejected = sum(1 for r in proposal_rows if r["Status"] in ("REJECTED", "EXPIRED"))

        ps1, ps2, ps3, ps4 = st.columns(4)
        with ps1:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Total</div><div class='metric-value'>{p_total}</div></div>", unsafe_allow_html=True)
        with ps2:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Pending</div><div class='metric-value' style='color:#FFA726;'>{p_pending}</div></div>", unsafe_allow_html=True)
        with ps3:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Executed</div><div class='metric-value' style='color:#00C853;'>{p_executed}</div></div>", unsafe_allow_html=True)
        with ps4:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>Rejected/Expired</div><div class='metric-value' style='color:#FF1744;'>{p_rejected}</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        def _color_proposal_status(val):
            colors = {
                "PENDING": "color:#FFA726;font-weight:700;",
                "APPROVED": "color:#00E5FF;font-weight:700;",
                "EXECUTED": "color:#00C853;font-weight:700;",
                "REJECTED": "color:#FF1744;font-weight:700;",
                "EXPIRED": "color:#888;font-weight:700;",
            }
            return colors.get(str(val), "")

        prop_df = pd.DataFrame(proposal_rows)
        styled_prop = prop_df.style.map(_color_proposal_status, subset=["Status"])
        st.dataframe(styled_prop, use_container_width=True, hide_index=True, height=420)
        _csv_download(prop_df, "trade_proposals", "csv_proposals")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 6 — APPROVAL EVENTS
# ─────────────────────────────────────────────────────────────────────────────
with tab_approvals:
    st.markdown("<div class='section-header'>✅ Approval Event Log</div>", unsafe_allow_html=True)
    action_filter = st.selectbox("Action", ["ALL", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED"], key="approval_action_filter")

    approval_rows = load_approval_events(action_filter)

    if not approval_rows:
        st.info("📊 No approval events yet. Approve or reject a proposal to see events here.")
    else:
        def _color_approval_action(val):
            colors = {
                "APPROVED": "color:#00C853;font-weight:700;",
                "EXECUTED": "color:#00E5FF;font-weight:700;",
                "REJECTED": "color:#FF1744;font-weight:700;",
                "EXPIRED": "color:#888;font-weight:700;",
            }
            return colors.get(str(val), "")

        appr_df = pd.DataFrame(approval_rows)
        styled_appr = appr_df.style.map(_color_approval_action, subset=["Action"])
        st.dataframe(styled_appr, use_container_width=True, hide_index=True, height=420)
        _csv_download(appr_df, "approval_events", "csv_approvals")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 7 — STOCK RANKINGS
# ─────────────────────────────────────────────────────────────────────────────
with tab_rankings:
    st.markdown("<div class='section-header'>📊 Stock Ranking History</div>", unsafe_allow_html=True)

    ranking_rows = load_stock_rankings()

    if not ranking_rows:
        st.info("📊 No ranking sessions yet. Run a scan on **Strategy Signals** or **US Market**.")
    else:
        rank_df = pd.DataFrame(ranking_rows)
        st.dataframe(rank_df, use_container_width=True, hide_index=True, height=420)
        _csv_download(rank_df, "stock_rankings", "csv_rankings")


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO REFRESH
# ═══════════════════════════════════════════════════════════════════════════════
if auto_refresh:
    import time
    time.sleep(10)
    st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='font-size:0.72rem;color:#555;text-align:center;line-height:1.7;'>
  📋 All events are automatically logged to the SQLite database (trading.db).<br>
  Logs persist across sessions and can be exported as CSV from each tab.<br>
  ⚠️ Not financial advice. This audit trail is for educational and review purposes only.
</div>
""", unsafe_allow_html=True)

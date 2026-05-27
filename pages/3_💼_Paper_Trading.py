"""
Paper Trading Page — full-featured order entry with risk controls.

Features
--------
* MockBroker fallback when no Alpaca API keys are configured.
* 6 trading modes displayed in sidebar dropdown.
* Kill switch in sidebar — prominent red, cancels pending orders.
* Full 12-check risk display before any order proceeds.
* Order entry form with estimated cost and risk preview.
* Positions table with color-coded unrealized P&L.
* Order history table.
* Wall Street terminal dark theme (gold/cyan accents).
"""

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Paper Trading | AI Trading Assistant",
    page_icon="💼",
    layout="wide",
)

# ── Wall Street Dark Theme CSS ────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
:root{
    --bg-primary:#0E1117;--bg-secondary:#131720;
    --accent-gold:#D4AF37;--accent-cyan:#00D4FF;
    --profit-green:#00C853;--loss-red:#FF1744;
    --text-primary:#E0E0E0;--text-muted:#888;
    --glass-bg:rgba(26,26,46,0.72);--glass-border:rgba(212,175,55,0.12);
}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}

.section-header{font-size:1.1rem;font-weight:700;color:#D4AF37;text-transform:uppercase;
    letter-spacing:1.5px;padding-bottom:0.5rem;margin-bottom:1rem;
    border-bottom:1px solid rgba(212,175,55,0.18);}
.metric-card{background:var(--glass-bg);backdrop-filter:blur(16px);
    border:1px solid var(--glass-border);border-radius:14px;padding:1.1rem 1.3rem;
    box-shadow:0 8px 32px rgba(0,0,0,0.45);position:relative;overflow:hidden;}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,#D4AF37,transparent);}
.metric-label{font-size:0.72rem;font-weight:700;text-transform:uppercase;
    letter-spacing:1.2px;color:#888;margin-bottom:0.25rem;}
.metric-value{font-size:1.6rem;font-weight:800;color:#fff;
    font-family:'JetBrains Mono',monospace;}
.gold-divider{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);
    margin:1.2rem 0;border:none;}

.risk-check-pass{background:rgba(0,200,83,0.08);border:1px solid rgba(0,200,83,0.3);
    border-radius:10px;padding:0.5rem 1rem;margin-bottom:0.25rem;
    font-size:0.8rem;color:#00C853;}
.risk-check-fail{background:rgba(255,23,68,0.08);border:1px solid rgba(255,23,68,0.3);
    border-radius:10px;padding:0.5rem 1rem;margin-bottom:0.25rem;
    font-size:0.8rem;color:#FF1744;}

.kill-banner{background:linear-gradient(135deg,rgba(255,23,68,0.25),rgba(255,23,68,0.08));
    border:2px solid #FF1744;border-radius:14px;padding:1.2rem 1.5rem;
    text-align:center;margin-bottom:1.2rem;animation:pulse-border 2s infinite;}
@keyframes pulse-border{0%,100%{border-color:#FF1744;}50%{border-color:#FF6090;}}

.sidebar-kill-btn button{background:linear-gradient(135deg,#FF1744,#D50000)!important;
    color:#fff!important;font-weight:800!important;border:none!important;
    border-radius:10px!important;padding:0.7rem!important;font-size:0.9rem!important;
    width:100%!important;letter-spacing:1px;}
.sidebar-kill-btn button:hover{box-shadow:0 0 20px rgba(255,23,68,0.5)!important;}

.sidebar-disengage-btn button{background:linear-gradient(135deg,#00C853,#00A844)!important;
    color:#fff!important;font-weight:800!important;border:none!important;
    border-radius:10px!important;padding:0.7rem!important;font-size:0.9rem!important;
    width:100%!important;letter-spacing:1px;}

.mode-warning{background:rgba(255,165,0,0.1);border:1px solid rgba(255,165,0,0.3);
    border-radius:8px;padding:0.5rem 0.8rem;font-size:0.78rem;color:#FFA000;margin-top:0.5rem;}
.mode-locked{background:rgba(255,23,68,0.08);border:1px solid rgba(255,23,68,0.25);
    border-radius:8px;padding:0.5rem 0.8rem;font-size:0.78rem;color:#FF1744;margin-top:0.5rem;}

.est-cost-box{background:rgba(212,175,55,0.08);border:1px solid rgba(212,175,55,0.2);
    border-radius:8px;padding:0.6rem 1rem;font-size:0.85rem;margin:0.3rem 0;}
</style>
""", unsafe_allow_html=True)

# ── Module imports with safe fallbacks ────────────────────────────────────────
try:
    from db.database import init_db, get_db_session
    from db.models import Order, AuditLog
    init_db()
    DB_OK = True
except Exception:
    DB_OK = False

try:
    from config.settings import get_settings
    settings = get_settings()
except Exception:
    settings = None

try:
    from trading.mock_broker import MockBroker
    MOCK_BROKER_OK = True
except Exception:
    MOCK_BROKER_OK = False

try:
    from trading.broker import AlpacaBroker
    ALPACA_BROKER_OK = True
except Exception:
    ALPACA_BROKER_OK = False

try:
    from trading.risk_manager import RiskManager
    RISK_OK = True
except Exception:
    RISK_OK = False

try:
    from trading.executor import TradingMode, TRADING_MODE_LABELS, LIVE_MODES
    EXECUTOR_OK = True
except Exception:
    EXECUTOR_OK = False

try:
    from trading.market_data import get_latest_price
    DATA_OK = True
except Exception:
    DATA_OK = False


# ── Broker Initialization ────────────────────────────────────────────────────
if "broker" not in st.session_state:
    st.session_state.broker = None
    if settings and settings.use_mock_broker:
        if MOCK_BROKER_OK:
            st.session_state.broker = MockBroker()
    elif settings and not settings.use_mock_broker:
        if ALPACA_BROKER_OK:
            try:
                st.session_state.broker = AlpacaBroker()
            except Exception:
                if MOCK_BROKER_OK:
                    st.session_state.broker = MockBroker()
    else:
        if MOCK_BROKER_OK:
            st.session_state.broker = MockBroker()

if "risk_manager" not in st.session_state:
    st.session_state.risk_manager = RiskManager() if RISK_OK else None

if "pt_orders" not in st.session_state:
    st.session_state.pt_orders = []

broker = st.session_state.broker
risk_manager = st.session_state.risk_manager
is_mock = isinstance(broker, MockBroker) if MOCK_BROKER_OK else True

# Show broker info banner
if is_mock:
    st.info("🔧 Running with **MockBroker** (no API keys configured). All trades are simulated in-memory.")

# ── Demo data fallbacks ──────────────────────────────────────────────────────
def demo_positions():
    return [
        {"symbol": "AAPL", "qty": 50, "side": "long", "avg_entry_price": 172.50,
         "current_price": 178.30, "unrealized_pl": 290.00, "market_value": 8915.00,
         "unrealized_plpc": 0.0336, "change_today": 0.42},
        {"symbol": "MSFT", "qty": 30, "side": "long", "avg_entry_price": 410.00,
         "current_price": 415.60, "unrealized_pl": 168.00, "market_value": 12468.00,
         "unrealized_plpc": 0.0137, "change_today": -0.12},
        {"symbol": "NVDA", "qty": 10, "side": "long", "avg_entry_price": 845.00,
         "current_price": 875.40, "unrealized_pl": 304.00, "market_value": 8754.00,
         "unrealized_plpc": 0.0360, "change_today": 1.85},
    ]

def demo_orders():
    return [
        {"id": "PPR-001", "symbol": "AAPL", "qty": 10, "side": "buy", "type": "market",
         "status": "filled", "filled_avg_price": 172.50, "submitted_at": str(datetime.now()), "mode": "paper"},
        {"id": "PPR-002", "symbol": "MSFT", "qty": 5, "side": "sell", "type": "limit",
         "status": "pending", "filled_avg_price": None, "submitted_at": str(datetime.now()), "mode": "paper"},
    ]

def demo_account():
    return {"equity": 100000.0, "buying_power": 200000.0, "cash": 100000.0, "daily_pnl": 0.0}


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Trading Mode, Kill Switch, Risk Status
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;margin-bottom:1rem;'>
        <span style='font-size:1.8rem;'>💼</span>
        <div style='font-size:1rem;font-weight:800;color:#D4AF37;margin-top:0.3rem;'>
            PAPER TRADING
        </div>
        <div style='font-size:0.7rem;color:#888;'>Order Execution Console</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Trading Mode Selector ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#D4AF37;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:0.5rem;'>"
                "⚙️ Trading Mode</div>", unsafe_allow_html=True)

    if EXECUTOR_OK:
        mode_options = list(TradingMode)
        mode_labels = []
        for m in mode_options:
            label = TRADING_MODE_LABELS.get(m, m.value)
            # Mark LIVE_AUTO as locked unless both flags are on
            if m == TradingMode.LIVE_AUTO:
                if settings and settings.ENABLE_LIVE_TRADING and settings.ENABLE_AUTO_LIVE_TRADING:
                    label = "Live — Auto (⚡ UNLOCKED)"
                else:
                    label = "Live — Auto (🔒 LOCKED)"
            mode_labels.append(label)

        selected_idx = st.selectbox(
            "Select Mode",
            range(len(mode_options)),
            format_func=lambda i: mode_labels[i],
            index=2,  # Default to AUTO_PAPER
            label_visibility="collapsed",
        )
        selected_mode = mode_options[selected_idx]

        # Warning for live modes
        if selected_mode in LIVE_MODES:
            st.markdown(
                "<div class='mode-warning'>⚠️ <strong>LIVE MODE</strong> — "
                "Real money may be at risk. Requires ENABLE_LIVE_TRADING=True.</div>",
                unsafe_allow_html=True,
            )
        if selected_mode == TradingMode.LIVE_AUTO:
            if not (settings and settings.ENABLE_LIVE_TRADING and settings.ENABLE_AUTO_LIVE_TRADING):
                st.markdown(
                    "<div class='mode-locked'>🔒 <strong>LOCKED</strong> — Requires both "
                    "ENABLE_LIVE_TRADING=True AND ENABLE_AUTO_LIVE_TRADING=True in .env</div>",
                    unsafe_allow_html=True,
                )
    else:
        selected_mode = None
        st.caption("Trading executor not loaded.")

    # ── Kill Switch ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#FF1744;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:0.5rem;'>"
                "🛑 Kill Switch</div>", unsafe_allow_html=True)

    ks_engaged = False
    if risk_manager:
        ks_engaged = risk_manager.kill_switch_engaged
    if broker and hasattr(broker, "kill_switch_engaged"):
        ks_engaged = ks_engaged or broker.kill_switch_engaged

    if ks_engaged:
        st.markdown(
            "<div style='background:rgba(255,23,68,0.15);border:1px solid #FF1744;"
            "border-radius:8px;padding:0.5rem;text-align:center;font-weight:700;"
            "color:#FF1744;font-size:0.9rem;margin-bottom:0.5rem;'>🛑 ENGAGED</div>",
            unsafe_allow_html=True,
        )
        with st.container():
            st.markdown("<div class='sidebar-disengage-btn'>", unsafe_allow_html=True)
            if st.button("✅ Disengage Kill Switch", key="disengage_ks", use_container_width=True):
                if risk_manager:
                    risk_manager.disengage_kill_switch()
                if broker and hasattr(broker, "disengage_kill_switch"):
                    broker.disengage_kill_switch()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='background:rgba(0,200,83,0.1);border:1px solid #00C853;"
            "border-radius:8px;padding:0.5rem;text-align:center;font-weight:700;"
            "color:#00C853;font-size:0.9rem;margin-bottom:0.5rem;'>✅ CLEAR</div>",
            unsafe_allow_html=True,
        )
        with st.container():
            st.markdown("<div class='sidebar-kill-btn'>", unsafe_allow_html=True)
            if st.button("🛑 ENGAGE KILL SWITCH", key="engage_ks", use_container_width=True):
                if risk_manager:
                    risk_manager.engage_kill_switch()
                if broker and hasattr(broker, "engage_kill_switch"):
                    broker.engage_kill_switch()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # ── Risk Status Summary ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#D4AF37;"
                "text-transform:uppercase;letter-spacing:1px;margin-bottom:0.5rem;'>"
                "🛡️ Risk Limits</div>", unsafe_allow_html=True)

    if risk_manager:
        try:
            risk_status = risk_manager.get_risk_status()
            limits = risk_status.get("limits", {})
            remaining = risk_status.get("remaining", {})
            st.markdown(f"""
            <div style='font-size:0.75rem;color:#CCC;line-height:1.8;'>
                <div>Max Daily Loss: <span style='color:#D4AF37;font-weight:700;'>${limits.get('max_daily_loss',100):,.0f}</span></div>
                <div>Max Position: <span style='color:#D4AF37;font-weight:700;'>${limits.get('max_position_size',500):,.0f}</span></div>
                <div>Max Trades/Day: <span style='color:#D4AF37;font-weight:700;'>{limits.get('max_trades_per_day',5)}</span></div>
                <div>Trades Remaining: <span style='color:#00C853;font-weight:700;'>{remaining.get('trades_remaining','—')}</span></div>
                <div>Loss Capacity: <span style='color:#00C853;font-weight:700;'>${remaining.get('loss_capacity',0):,.2f}</span></div>
                <div>Cooldown: <span style='color:#D4AF37;font-weight:700;'>{limits.get('cooldown_seconds',300)}s</span></div>
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            st.caption("Risk status unavailable.")
    else:
        st.caption("Risk manager not loaded.")

    # ── Mock Broker Test Prices ───────────────────────────────────────────────
    if is_mock and broker:
        st.markdown("---")
        st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#00D4FF;"
                    "text-transform:uppercase;letter-spacing:1px;margin-bottom:0.5rem;'>"
                    "🧪 Mock Price Injection</div>", unsafe_allow_html=True)
        with st.form("mock_price_form"):
            mock_ticker = st.text_input("Ticker", value="AAPL").upper().strip()
            mock_price = st.number_input("Price ($)", min_value=0.01, value=175.00, step=0.01)
            if st.form_submit_button("Set Price", use_container_width=True):
                broker.set_price(mock_ticker, mock_price)
                st.success(f"Set {mock_ticker} = ${mock_price:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════════════════════

# ── Kill Switch Banner (if engaged) ──────────────────────────────────────────
if ks_engaged:
    st.markdown("""
    <div class='kill-banner'>
        <div style='font-size:2rem;font-weight:900;color:#FF1744;'>🛑 KILL SWITCH ENGAGED</div>
        <div style='font-size:0.95rem;color:#FF6090;margin-top:0.3rem;'>
            All trading is halted. Pending orders have been cancelled.
            Disengage the kill switch in the sidebar to resume trading.
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
mode_badge_color = "#00C853" if is_mock else "#FFA000"
mode_label = "📄 PAPER (Mock)" if is_mock else "📄 PAPER"
if selected_mode and EXECUTOR_OK and selected_mode in LIVE_MODES:
    mode_badge_color = "#FF1744"
    mode_label = "🔴 LIVE"

st.markdown(f"""
<div style='margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;'>
  <div>
    <h1 style='margin:0;font-size:2rem;font-weight:900;
        background:linear-gradient(135deg,#D4AF37,#F5E6A3);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
        💼 Paper Trading
    </h1>
    <p style='margin:0;color:#888;font-size:0.9rem;'>Place and manage paper trades with full risk controls</p>
  </div>
  <div style='background:rgba(0,200,83,0.1);border:2px solid {mode_badge_color};
      border-radius:10px;padding:0.4rem 1rem;text-align:center;'>
    <div style='font-size:0.7rem;color:#888;text-transform:uppercase;'>Mode</div>
    <div style='font-size:1rem;font-weight:800;color:{mode_badge_color};'>{mode_label}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Account Summary ──────────────────────────────────────────────────────────
account = demo_account()
if broker:
    try:
        account = broker.get_account()
    except Exception:
        pass

a1, a2, a3, a4 = st.columns(4)
daily_pnl = account.get("daily_pnl", 0)
pnl_color = "#00C853" if daily_pnl >= 0 else "#FF1744"

with a1:
    st.markdown(f"<div class='metric-card'><div class='metric-label'>Portfolio Value</div>"
                f"<div class='metric-value'>${account.get('equity', 0):,.2f}</div></div>",
                unsafe_allow_html=True)
with a2:
    st.markdown(f"<div class='metric-card'><div class='metric-label'>Buying Power</div>"
                f"<div class='metric-value'>${account.get('buying_power', 0):,.2f}</div></div>",
                unsafe_allow_html=True)
with a3:
    sign = "+" if daily_pnl >= 0 else ""
    st.markdown(f"<div class='metric-card'><div class='metric-label'>Daily P&L</div>"
                f"<div class='metric-value' style='color:{pnl_color};'>{sign}${daily_pnl:,.2f}</div></div>",
                unsafe_allow_html=True)
with a4:
    cash_val = account.get("cash", 0)
    st.markdown(f"<div class='metric-card'><div class='metric-label'>Cash</div>"
                f"<div class='metric-value'>${cash_val:,.2f}</div></div>",
                unsafe_allow_html=True)

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── Main Layout: Order Form | Positions & History ─────────────────────────────
col_form, col_right = st.columns([1.2, 1.8])

with col_form:
    st.markdown("<div class='section-header'>📝 Place Order</div>", unsafe_allow_html=True)

    with st.form("paper_order_form"):
        f_ticker = st.text_input("Ticker Symbol", value="AAPL").upper().strip()
        f_side = st.radio("Side", ["Buy", "Sell"], horizontal=True)
        f_qty = st.number_input("Quantity (shares)", min_value=1, value=10, step=1)
        f_order_type = st.selectbox("Order Type", ["market", "limit"])
        f_limit_price = None
        if f_order_type == "limit":
            f_limit_price = st.number_input("Limit Price ($)", min_value=0.01, value=100.00, step=0.01)

        # ── Estimated cost ────────────────────────────────────────────────────
        latest_price = None
        # Try to get price from broker first (MockBroker has set_price)
        if broker and hasattr(broker, "_get_price"):
            try:
                latest_price = broker._get_price(f_ticker)
            except Exception:
                pass
        if latest_price is None and DATA_OK:
            try:
                latest_price = get_latest_price(f_ticker)
            except Exception:
                pass
        if latest_price is None:
            latest_price = f_limit_price or 150.0

        est_cost = f_qty * latest_price
        st.markdown(
            f"<div class='est-cost-box'>"
            f"<span style='color:#888;'>Est. Cost:</span> "
            f"<span style='font-weight:700;color:#D4AF37;font-family:JetBrains Mono,monospace;'>"
            f"${est_cost:,.2f}</span> "
            f"<span style='color:#888;'>@ ${latest_price:.2f}/share</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        submitted = st.form_submit_button(
            "🚀 Place Paper Order",
            use_container_width=True,
            type="primary",
            disabled=ks_engaged,
        )

    # ── Process order submission ──────────────────────────────────────────────
    if submitted:
        if ks_engaged:
            st.error("🛑 Kill switch is engaged. All trading is halted. Disengage the kill switch to place orders.")
        else:
            side_str = f_side.lower()

            # ── Risk Check (MANDATORY — AI can NEVER override) ────────────────
            st.markdown("<div class='section-header' style='margin-top:1rem;'>🛡️ Risk Check — All 12 Checks</div>",
                        unsafe_allow_html=True)

            risk_result = None
            risk_approved = False

            if risk_manager:
                try:
                    risk_result = risk_manager.check_order(
                        symbol=f_ticker,
                        qty=float(f_qty),
                        side=side_str,
                        price=latest_price,
                        account_buying_power=account.get("buying_power", 50000),
                        mode=selected_mode.value if selected_mode else "paper",
                        market_data_available=(latest_price is not None and latest_price > 0),
                    )
                    risk_approved = risk_result.approved
                except Exception as e:
                    st.error(f"⚠️ Risk check error: {e}")

                # Display all 12 checks
                if risk_result:
                    check_col1, check_col2 = st.columns(2)
                    all_checks = (
                        [(c, True) for c in risk_result.checks_passed] +
                        [(c, False) for c in risk_result.checks_failed]
                    )
                    mid = (len(all_checks) + 1) // 2
                    with check_col1:
                        for i, (check, passed) in enumerate(all_checks[:mid]):
                            css_class = "risk-check-pass" if passed else "risk-check-fail"
                            icon = "✅" if passed else "❌"
                            st.markdown(f"<div class='{css_class}'>{icon} {check}</div>",
                                        unsafe_allow_html=True)
                    with check_col2:
                        for i, (check, passed) in enumerate(all_checks[mid:]):
                            css_class = "risk-check-pass" if passed else "risk-check-fail"
                            icon = "✅" if passed else "❌"
                            st.markdown(f"<div class='{css_class}'>{icon} {check}</div>",
                                        unsafe_allow_html=True)

                    # Show verdict
                    if risk_approved:
                        st.markdown(
                            "<div style='background:rgba(0,200,83,0.1);border:2px solid #00C853;"
                            "border-radius:10px;padding:0.6rem 1rem;text-align:center;margin-top:0.5rem;'>"
                            "<span style='color:#00C853;font-weight:800;font-size:1rem;'>"
                            "✅ ALL CHECKS PASSED — Order approved</span></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='background:rgba(255,23,68,0.1);border:2px solid #FF1744;"
                            "border-radius:10px;padding:0.6rem 1rem;text-align:center;margin-top:0.5rem;'>"
                            "<span style='color:#FF1744;font-weight:800;font-size:1rem;'>"
                            "🚫 RISK CHECK FAILED — Order blocked</span></div>",
                            unsafe_allow_html=True,
                        )

                # ── Place order only if risk approved ─────────────────────────
                if risk_approved:
                    if broker:
                        try:
                            order_kwargs = {
                                "symbol": f_ticker,
                                "qty": float(f_qty),
                                "side": side_str,
                                "order_type": f_order_type,
                                "time_in_force": "day",
                            }
                            if f_limit_price:
                                order_kwargs["limit_price"] = f_limit_price
                            order_res = broker.place_order(**order_kwargs)

                            if order_res.get("error"):
                                st.error(f"❌ Broker rejected: {order_res['error']}")
                            else:
                                st.success(
                                    f"✅ Order submitted! ID: {order_res.get('id', 'N/A')} | "
                                    f"Status: {order_res.get('status', 'submitted')} | "
                                    f"Fill: ${order_res.get('filled_avg_price', 0) or 0:.2f}"
                                )
                        except Exception as e:
                            st.error(f"❌ Order failed: {e}")
                    else:
                        # No broker: record demo order
                        fake_order = {
                            "id": f"DEMO-{len(st.session_state.pt_orders) + 1:03d}",
                            "symbol": f_ticker, "qty": f_qty, "side": side_str,
                            "type": f_order_type, "status": "filled (demo)",
                            "filled_avg_price": latest_price,
                            "submitted_at": str(datetime.now()), "mode": "paper",
                        }
                        st.session_state.pt_orders.append(fake_order)
                        st.success(
                            f"✅ Demo order: {side_str.upper()} {f_qty}x {f_ticker} @ ${latest_price:.2f}"
                        )
                elif risk_result:
                    st.error("🚫 Order BLOCKED by risk manager. The AI can never override risk checks. "
                             "Review the failed checks above.")
            else:
                # No risk manager — allow demo orders with warning
                fake_order = {
                    "id": f"DEMO-{len(st.session_state.pt_orders) + 1:03d}",
                    "symbol": f_ticker, "qty": f_qty, "side": side_str,
                    "type": f_order_type, "status": "demo",
                    "filled_avg_price": latest_price,
                    "submitted_at": str(datetime.now()), "mode": "paper",
                }
                st.session_state.pt_orders.append(fake_order)
                st.warning("⚠️ Risk manager not initialized. Order recorded as demo.")
                st.markdown(
                    "<div class='risk-check-fail'>❌ Risk manager unavailable — "
                    "12 safety checks could not be run.</div>",
                    unsafe_allow_html=True,
                )


with col_right:
    # ── Positions Table ───────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📊 Open Positions</div>", unsafe_allow_html=True)

    positions = []
    if broker:
        try:
            positions = broker.get_positions()
        except Exception:
            positions = demo_positions() if not is_mock else []
    else:
        positions = demo_positions()

    if positions:
        pos_rows = []
        for p in positions:
            pl = float(p.get("unrealized_pl", 0) or 0)
            plpc = float(p.get("unrealized_plpc", 0) or 0)
            sign = "+" if pl >= 0 else ""
            pos_rows.append({
                "Symbol": p.get("symbol", ""),
                "Qty": p.get("qty", 0),
                "Side": str(p.get("side", "long")).upper(),
                "Avg Entry": f"${float(p.get('avg_entry_price', 0)):.2f}",
                "Current": f"${float(p.get('current_price', 0)):.2f}",
                "Market Val.": f"${float(p.get('market_value', 0)):,.2f}",
                "Unreal. P&L": f"{sign}${pl:,.2f}",
                "Return": f"{sign}{plpc * 100:.2f}%",
            })

        pos_df = pd.DataFrame(pos_rows)

        def color_pnl(val):
            if isinstance(val, str):
                if val.startswith("+"):
                    return "color:#00C853;font-weight:700;"
                elif val.startswith("-"):
                    return "color:#FF1744;font-weight:700;"
            return ""

        st.dataframe(
            pos_df.style.map(color_pnl, subset=["Unreal. P&L", "Return"]),
            use_container_width=True,
            hide_index=True,
        )

        # P&L summary
        total_pl = sum(float(p.get("unrealized_pl", 0) or 0) for p in positions)
        total_mv = sum(float(p.get("market_value", 0) or 0) for p in positions)
        pl_color = "#00C853" if total_pl >= 0 else "#FF1744"
        sign = "+" if total_pl >= 0 else ""
        st.markdown(
            f"<div style='text-align:right;font-size:0.85rem;color:#888;margin-top:0.4rem;'>"
            f"Total Market Value: <span style='color:#E0E0E0;font-weight:700;'>${total_mv:,.2f}</span>"
            f" &nbsp;|&nbsp; Total Unrealized P&L: "
            f"<span style='color:{pl_color};font-weight:700;'>{sign}${total_pl:,.2f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='background:rgba(26,26,46,0.6);border:1px solid rgba(212,175,55,0.1);"
            "border-radius:10px;padding:1.5rem;text-align:center;color:#888;'>"
            "No open positions. Place an order to get started."
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── Order History ─────────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📋 Order History</div>", unsafe_allow_html=True)

    orders = []
    if broker:
        try:
            orders = broker.get_orders(status="all", limit=20)
        except Exception:
            orders = demo_orders()
    else:
        orders = demo_orders() + list(reversed(st.session_state.pt_orders[-10:]))

    # Also include session-state demo orders if broker is mock but has no orders
    if not orders and st.session_state.pt_orders:
        orders = list(reversed(st.session_state.pt_orders[-10:]))

    if orders:
        order_rows = []
        for o in orders:
            fill = o.get("filled_avg_price") or o.get("fill_price")
            fill_str = f"${float(fill):.2f}" if fill else "—"
            ts = o.get("submitted_at") or o.get("created_at") or ""
            if ts:
                try:
                    ts = str(ts)[:16]
                except Exception:
                    pass
            status_raw = o.get("status", "")
            # Color the status in the data
            order_rows.append({
                "ID": str(o.get("id", ""))[:12],
                "Symbol": o.get("symbol", ""),
                "Side": (o.get("side", "") or "").upper(),
                "Qty": o.get("qty", 0),
                "Type": o.get("type") or o.get("order_type", ""),
                "Status": status_raw,
                "Fill Price": fill_str,
                "Time": ts,
            })

        ord_df = pd.DataFrame(order_rows)

        def color_side(val):
            if val == "BUY":
                return "color:#00C853;font-weight:700;"
            elif val == "SELL":
                return "color:#FF1744;font-weight:700;"
            return ""

        def color_status(val):
            v = str(val).lower()
            if "fill" in v:
                return "color:#00C853;"
            elif "cancel" in v or "reject" in v:
                return "color:#FF1744;"
            return "color:#D4AF37;"

        st.dataframe(
            ord_df.style.map(color_side, subset=["Side"])
                  .map(color_status, subset=["Status"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.markdown(
            "<div style='background:rgba(26,26,46,0.6);border:1px solid rgba(212,175,55,0.1);"
            "border-radius:10px;padding:1.5rem;text-align:center;color:#888;'>"
            "No orders yet. Place a trade to see order history."
            "</div>",
            unsafe_allow_html=True,
        )


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='font-size:0.72rem;color:#555;text-align:center;padding:0.5rem;'>
⚠️ Paper trading uses simulated funds. No real money is at risk unless
LIVE mode is explicitly enabled in your .env configuration.<br>
This is for educational and practice purposes only. Not financial advice.
The AI analyst is advisory only — it can <strong>NEVER</strong> override the risk manager.
</div>
""", unsafe_allow_html=True)

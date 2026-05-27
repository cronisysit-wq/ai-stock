"""
AI Trading Assistant — Main Dashboard
Premium Wall Street Terminal-Style Streamlit App
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import json
import traceback

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Trading Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Premium CSS ──────────────────────────────────────────────────────────────
PREMIUM_CSS = """
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Root Variables ── */
:root {
    --bg-primary: #0E1117;
    --bg-card: #1A1A2E;
    --bg-card-hover: #22223A;
    --accent-gold: #D4AF37;
    --accent-gold-dim: rgba(212,175,55,0.15);
    --profit-green: #00C853;
    --loss-red: #FF1744;
    --text-primary: #E0E0E0;
    --text-muted: #888888;
    --text-bright: #FFFFFF;
    --border-subtle: rgba(212,175,55,0.18);
    --glass-bg: rgba(26,26,46,0.72);
    --glass-border: rgba(212,175,55,0.12);
    --glass-shadow: 0 8px 32px rgba(0,0,0,0.45);
}

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary);
}

.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}

/* ── Hide Streamlit chrome ── */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: rgba(14,17,23,0.85); backdrop-filter: blur(12px);}

/* ── Scrollbar ── */
::-webkit-scrollbar {width: 6px; height: 6px;}
::-webkit-scrollbar-track {background: var(--bg-primary);}
::-webkit-scrollbar-thumb {background: var(--accent-gold-dim); border-radius: 3px;}
::-webkit-scrollbar-thumb:hover {background: var(--accent-gold);}

/* ── Glassmorphism Metric Card ── */
.metric-card {
    background: var(--glass-bg);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    box-shadow: var(--glass-shadow);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--accent-gold), transparent);
    border-radius: 16px 16px 0 0;
}
.metric-card:hover {
    border-color: rgba(212,175,55,0.35);
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.55);
}
.metric-card .metric-label {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
}
.metric-card .metric-value {
    font-size: 1.85rem;
    font-weight: 800;
    color: var(--text-bright);
    line-height: 1.1;
    font-family: 'JetBrains Mono', monospace;
}
.metric-card .metric-delta {
    font-size: 0.82rem;
    font-weight: 600;
    margin-top: 0.3rem;
}
.metric-delta.positive {color: var(--profit-green);}
.metric-delta.negative {color: var(--loss-red);}

/* ── Section Headers ── */
.section-header {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--accent-gold);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding-bottom: 0.6rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border-subtle);
}

/* ── Signal Badge ── */
.signal-badge {
    display: inline-block;
    padding: 0.6rem 2rem;
    border-radius: 50px;
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: 2px;
    text-transform: uppercase;
    text-align: center;
}
.signal-buy {
    background: linear-gradient(135deg, rgba(0,200,83,0.2), rgba(0,200,83,0.05));
    color: var(--profit-green);
    border: 2px solid var(--profit-green);
    box-shadow: 0 0 20px rgba(0,200,83,0.15);
}
.signal-sell {
    background: linear-gradient(135deg, rgba(255,23,68,0.2), rgba(255,23,68,0.05));
    color: var(--loss-red);
    border: 2px solid var(--loss-red);
    box-shadow: 0 0 20px rgba(255,23,68,0.15);
}
.signal-hold {
    background: linear-gradient(135deg, rgba(212,175,55,0.2), rgba(212,175,55,0.05));
    color: var(--accent-gold);
    border: 2px solid var(--accent-gold);
    box-shadow: 0 0 20px rgba(212,175,55,0.15);
}

/* ── Confidence Meter ── */
.confidence-bar-bg {
    background: rgba(255,255,255,0.06);
    border-radius: 10px;
    height: 14px;
    overflow: hidden;
    margin-top: 0.4rem;
}
.confidence-bar-fill {
    height: 100%;
    border-radius: 10px;
    transition: width 0.8s ease;
}

/* ── Glass Panel ── */
.glass-panel {
    background: var(--glass-bg);
    backdrop-filter: blur(14px);
    border: 1px solid var(--glass-border);
    border-radius: 14px;
    padding: 1.5rem;
    box-shadow: var(--glass-shadow);
    margin-bottom: 1rem;
}

/* ── Live Warning Pulse ── */
@keyframes pulse-red {
    0%, 100% {opacity: 1; box-shadow: 0 0 20px rgba(255,23,68,0.4);}
    50% {opacity: 0.85; box-shadow: 0 0 40px rgba(255,23,68,0.7);}
}
.live-warning {
    background: linear-gradient(90deg, rgba(255,23,68,0.18), rgba(255,23,68,0.08));
    border: 2px solid var(--loss-red);
    border-radius: 12px;
    padding: 1rem 1.5rem;
    text-align: center;
    font-weight: 800;
    font-size: 1.1rem;
    color: var(--loss-red);
    animation: pulse-red 2s ease-in-out infinite;
    margin-bottom: 1.2rem;
    letter-spacing: 1px;
}

/* ── Emergency Stop Button ── */
.emergency-btn {
    background: linear-gradient(135deg, #D32F2F, #B71C1C) !important;
    color: white !important;
    border: 2px solid #FF1744 !important;
    border-radius: 12px !important;
    font-weight: 800 !important;
    font-size: 1rem !important;
    letter-spacing: 1px !important;
    padding: 0.8rem 1.5rem !important;
    width: 100% !important;
    text-transform: uppercase !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 20px rgba(255,23,68,0.3) !important;
}
.emergency-btn:hover {
    box-shadow: 0 6px 30px rgba(255,23,68,0.55) !important;
    transform: scale(1.02) !important;
}

/* ── Sidebar styling ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E1117 0%, #12121F 100%);
    border-right: 1px solid var(--border-subtle);
}
section[data-testid="stSidebar"] .stRadio > label {
    color: var(--text-primary) !important;
}

/* ── Data table styling ── */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}
.stDataFrame [data-testid="stDataFrameResizable"] {
    border: 1px solid var(--glass-border);
    border-radius: 12px;
}

/* ── Progress bars ── */
.stProgress > div > div {
    background-color: var(--accent-gold) !important;
    border-radius: 10px;
}

/* ── Buttons ── */
.stButton > button {
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button:hover {
    border-color: var(--accent-gold);
    box-shadow: 0 0 15px var(--accent-gold-dim);
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    border-bottom: 1px solid var(--border-subtle);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.stTabs [aria-selected="true"] {
    border-bottom: 2px solid var(--accent-gold) !important;
    color: var(--accent-gold) !important;
}

/* ── Divider ── */
.gold-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-gold), transparent);
    margin: 1.5rem 0;
    border: none;
}

/* ── Disclaimer ── */
.disclaimer {
    font-size: 0.72rem;
    color: var(--text-muted);
    text-align: center;
    padding: 1.5rem;
    border-top: 1px solid var(--glass-border);
    margin-top: 2rem;
    line-height: 1.6;
}
</style>
"""
st.markdown(PREMIUM_CSS, unsafe_allow_html=True)

# ── Imports & Init ───────────────────────────────────────────────────────────
try:
    from db.database import init_db, get_db_session
    from db.models import Signal, Order, AuditLog, TradeLog
    init_db()
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

try:
    from config.settings import get_settings
    settings = get_settings()
except Exception:
    settings = None

try:
    from trading.broker import AlpacaBroker
    from trading.mock_broker import MockBroker
    from trading.risk_manager import RiskManager
    from trading.executor import TradeExecutor, TradingMode, TRADING_MODE_LABELS, LIVE_MODES
    TRADING_AVAILABLE = True
except Exception:
    TRADING_AVAILABLE = False

try:
    from trading.market_data import get_historical_data, add_indicators, get_latest_price
    from trading.strategies import get_strategy, get_all_strategies, SignalType
    DATA_AVAILABLE = True
except Exception:
    DATA_AVAILABLE = False

try:
    from ai.analyst import explain_signal
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False


# ── Demo / Fallback Data ────────────────────────────────────────────────────
def get_demo_account():
    return {
        "equity": 100000.00, "buying_power": 50000.00, "cash": 50000.00,
        "portfolio_value": 100000.00, "daily_pnl": 250.00, "status": "DEMO",
    }


def get_demo_positions():
    return [
        {"symbol": "AAPL", "qty": 50, "avg_entry_price": 172.50, "current_price": 178.30,
         "unrealized_pl": 290.00, "market_value": 8915.00, "side": "long"},
        {"symbol": "MSFT", "qty": 30, "avg_entry_price": 410.00, "current_price": 415.60,
         "unrealized_pl": 168.00, "market_value": 12468.00, "side": "long"},
    ]


def get_demo_orders():
    return [
        {"id": "demo-001", "symbol": "AAPL", "qty": 10, "side": "buy", "type": "market",
         "status": "filled", "filled_avg_price": 178.30, "submitted_at": "2026-05-23 14:30"},
        {"id": "demo-002", "symbol": "GOOGL", "qty": 5, "side": "buy", "type": "limit",
         "status": "new", "filled_avg_price": None, "submitted_at": "2026-05-23 14:45"},
        {"id": "demo-003", "symbol": "TSLA", "qty": 15, "side": "sell", "type": "market",
         "status": "filled", "filled_avg_price": 252.10, "submitted_at": "2026-05-23 13:10"},
    ]


def get_demo_chart_data(symbol: str = "AAPL"):
    import numpy as np
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=120, freq="B")
    base = 175.0
    close = base + np.cumsum(np.random.randn(120) * 1.8)
    df = pd.DataFrame({
        "open": close + np.random.randn(120) * 0.5,
        "high": close + abs(np.random.randn(120) * 1.5),
        "low": close - abs(np.random.randn(120) * 1.5),
        "close": close,
        "volume": np.random.randint(20_000_000, 80_000_000, 120),
    }, index=dates)
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["rsi"] = 50 + np.random.randn(120) * 12
    return df


# ── Session State Init ──────────────────────────────────────────────────────
if "broker" not in st.session_state:
    st.session_state.broker = None
    if TRADING_AVAILABLE:
        try:
            if settings and settings.use_mock_broker:
                st.session_state.broker = MockBroker()
            else:
                st.session_state.broker = AlpacaBroker()
        except Exception:
            try:
                st.session_state.broker = MockBroker()
            except Exception:
                pass

if "risk_manager" not in st.session_state:
    st.session_state.risk_manager = None
    if TRADING_AVAILABLE:
        try:
            st.session_state.risk_manager = RiskManager()
        except Exception:
            pass

if "executor" not in st.session_state:
    st.session_state.executor = None
    if st.session_state.broker and st.session_state.risk_manager:
        try:
            st.session_state.executor = TradeExecutor(
                st.session_state.broker, st.session_state.risk_manager
            )
        except Exception:
            pass

if "trading_mode" not in st.session_state:
    st.session_state.trading_mode = TradingMode.MANUAL if TRADING_AVAILABLE else "manual"

if "kill_switch" not in st.session_state:
    st.session_state.kill_switch = False

broker = st.session_state.broker
risk_manager = st.session_state.risk_manager
executor = st.session_state.executor
is_mock = hasattr(broker, '_initial_capital')  # MockBroker has this attribute

# ── Helpers ──────────────────────────────────────────────────────────────────
def fmt_currency(val):
    if val is None:
        return "$0.00"
    return f"${val:,.2f}"

def fmt_pnl(val):
    if val is None:
        val = 0
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:,.2f}"

def get_account_data():
    if broker:
        try:
            return broker.get_account()
        except Exception:
            return get_demo_account()
    return get_demo_account()


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='text-align:center; padding:0.8rem 0 1.2rem;'>"
        "<span style='font-size:2.2rem;'>🤖</span><br>"
        "<span style='font-size:1.1rem; font-weight:800; color:#D4AF37; letter-spacing:2px;'>"
        "AI TRADING ASSISTANT</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ─ Trading Mode ─
    st.markdown(
        "<p style='font-size:0.8rem;font-weight:700;color:#D4AF37;"
        "text-transform:uppercase;letter-spacing:1.2px;margin-bottom:0.3rem;'>"
        "Trading Mode</p>",
        unsafe_allow_html=True,
    )

    if TRADING_AVAILABLE:
        mode_options = list(TradingMode)
        mode_labels = [TRADING_MODE_LABELS.get(m, m.value) for m in mode_options]
        selected_idx = st.selectbox(
            "mode", range(len(mode_labels)),
            format_func=lambda i: mode_labels[i],
            label_visibility="collapsed",
        )
        selected_mode = mode_options[selected_idx]
        st.session_state.trading_mode = selected_mode

        if selected_mode in LIVE_MODES:
            if settings and not settings.ENABLE_LIVE_TRADING:
                st.error("🔒 Live trading LOCKED — set ENABLE_LIVE_TRADING=true in .env")
            else:
                st.warning("⚠️ Live mode — REAL MONEY at risk")

        if selected_mode == TradingMode.LIVE_AUTO:
            if settings and not settings.is_live_auto_trading_allowed:
                st.error("🔒 Live-Auto LOCKED — requires ENABLE_LIVE_TRADING=true AND ENABLE_AUTO_LIVE_TRADING=true")

        if selected_mode == TradingMode.AUTO_PAPER and settings and not settings.ENABLE_AUTO_MODE:
            st.warning("⚠️ Auto paper mode disabled — set ENABLE_AUTO_MODE=true in .env")
    else:
        st.info("Manual mode (trading modules not loaded)")
        st.session_state.trading_mode = "manual"

    # Broker indicator
    if is_mock:
        st.markdown(
            "<div style='background:rgba(0,200,83,0.1);border:1px solid rgba(0,200,83,0.3);"
            "border-radius:8px;padding:0.4rem 0.6rem;text-align:center;margin:0.3rem 0;'>"
            "<span style='font-size:0.75rem;color:#00C853;font-weight:600;'>🔧 MockBroker Active</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    elif broker:
        label = "📡 Alpaca Connected"
        st.markdown(
            f"<div style='background:rgba(212,175,55,0.1);border:1px solid rgba(212,175,55,0.3);"
            f"border-radius:8px;padding:0.4rem 0.6rem;text-align:center;margin:0.3rem 0;'>"
            f"<span style='font-size:0.75rem;color:#D4AF37;font-weight:600;'>{label}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ─ Ticker / Strategy / Qty ─
    st.markdown(
        "<p style='font-size:0.8rem;font-weight:700;color:#D4AF37;"
        "text-transform:uppercase;letter-spacing:1.2px;margin-bottom:0.3rem;'>"
        "Trade Parameters</p>",
        unsafe_allow_html=True,
    )
    ticker = st.text_input("Ticker Symbol", value="AAPL", placeholder="e.g. AAPL")
    ticker = ticker.upper().strip()

    strategy_names = []
    if DATA_AVAILABLE:
        try:
            strategy_names = [s.__class__.__name__ for s in get_all_strategies()]
        except Exception:
            pass
    if not strategy_names:
        strategy_names = ["MACD Crossover", "RSI Reversal", "SMA Crossover", "VWAP Bounce"]
    selected_strategy = st.selectbox("Strategy", strategy_names)
    quantity = st.number_input("Quantity", min_value=1, value=10, step=1)

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ─ Kill Switch ─
    st.markdown(
        "<p style='font-size:0.8rem;font-weight:700;color:#FF1744;"
        "text-transform:uppercase;letter-spacing:1.2px;margin-bottom:0.3rem;'>"
        "🚨 Emergency Controls</p>",
        unsafe_allow_html=True,
    )
    kill_engaged = st.session_state.kill_switch
    if kill_engaged:
        st.error("🛑 KILL SWITCH ACTIVE — All trading halted")
        if st.button("🔓 Disengage Kill Switch", use_container_width=True):
            st.session_state.kill_switch = False
            if broker:
                try:
                    broker.disengage_kill_switch()
                except Exception:
                    pass
            if risk_manager:
                try:
                    risk_manager.disengage_kill_switch()
                except Exception:
                    pass
            st.rerun()
    else:
        if st.button("🛑 EMERGENCY STOP", use_container_width=True, type="primary"):
            st.session_state.kill_switch = True
            if broker:
                try:
                    broker.engage_kill_switch()
                except Exception:
                    pass
            if risk_manager:
                try:
                    risk_manager.engage_kill_switch()
                except Exception:
                    pass
            st.rerun()

    st.markdown(
        "<div style='text-align:center; padding-top:1rem;'>"
        "<span style='font-size:0.68rem;color:#888;'>v1.0.0 · Built with Streamlit</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Header ───────────────────────────────────────────────────────────────────
is_live = settings and hasattr(settings, "is_live_trading") and settings.is_live_trading
is_live_auto = settings and hasattr(settings, "is_live_auto_trading_allowed") and settings.is_live_auto_trading_allowed

if is_live:
    st.markdown(
        "<div class='live-warning'>"
        "🚨 LIVE TRADING MODE ACTIVE — REAL MONEY AT RISK 🚨"
        "</div>",
        unsafe_allow_html=True,
    )
    if is_live_auto:
        st.markdown(
            "<div class='live-warning' style='border-color:#FF6F00;color:#FF6F00;'>"
            "⚡ LIVE AUTO-TRADING ENABLED — Orders execute without manual approval"
            "</div>",
            unsafe_allow_html=True,
        )

if is_mock:
    trading_mode_str = "🔧 MockBroker (Demo Mode)"
elif is_live:
    trading_mode_str = "🔴 LIVE Trading Mode"
else:
    trading_mode_str = "Paper Trading Mode"

st.markdown(
    f"""
    <div style='margin-bottom:1.2rem;'>
        <h1 style='margin:0; font-size:2.2rem; font-weight:900;
            background: linear-gradient(135deg, #D4AF37, #F5E6A3);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            letter-spacing:1px;'>
            AI Trading Assistant
        </h1>
        <p style='margin:0; color:#888; font-size:0.9rem; letter-spacing:0.5px;'>
            AI-Powered Trading Assistant &nbsp;|&nbsp; {trading_mode_str}
            &nbsp;|&nbsp; {datetime.now().strftime("%b %d, %Y  %H:%M")}
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Top Metrics ──────────────────────────────────────────────────────────────
account = get_account_data()
equity = account.get("equity", 0)
buying_power = account.get("buying_power", 0)
daily_pnl = account.get("daily_pnl", 0)
positions_list = []
if broker:
    try:
        positions_list = broker.get_positions()
    except Exception:
        positions_list = get_demo_positions()
else:
    positions_list = get_demo_positions()

pnl_class = "positive" if daily_pnl >= 0 else "negative"
pnl_icon = "▲" if daily_pnl >= 0 else "▼"

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Portfolio Value</div>
            <div class='metric-value'>{fmt_currency(equity)}</div>
            <div class='metric-delta {pnl_class}'>{pnl_icon} {fmt_pnl(daily_pnl)} today</div>
        </div>""",
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Buying Power</div>
            <div class='metric-value'>{fmt_currency(buying_power)}</div>
            <div class='metric-delta' style='color:var(--text-muted);'>Available to trade</div>
        </div>""",
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Daily P&L</div>
            <div class='metric-value' style='color:{"var(--profit-green)" if daily_pnl >= 0 else "var(--loss-red)"};'>
                {fmt_pnl(daily_pnl)}
            </div>
            <div class='metric-delta {pnl_class}'>
                {pnl_icon} {abs(daily_pnl / max(equity, 1) * 100):.2f}%
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Open Positions</div>
            <div class='metric-value'>{len(positions_list)}</div>
            <div class='metric-delta' style='color:var(--text-muted);'>Active trades</div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── Main Content: Chart + Signal ─────────────────────────────────────────────
col_chart, col_signal = st.columns([2.2, 1])

with col_chart:
    st.markdown("<div class='section-header'>📊 Price Action & Indicators</div>", unsafe_allow_html=True)

    df = None
    if DATA_AVAILABLE:
        try:
            df = get_historical_data(
                ticker,
                start=(datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"),
                end=datetime.now().strftime("%Y-%m-%d"),
                period=None,
                interval="1d",
            )
            df = add_indicators(df)
        except Exception:
            df = None

    if df is None or df.empty:
        df = get_demo_chart_data(ticker)

    fig = go.Figure()

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            increasing_line_color="#00C853", decreasing_line_color="#FF1744",
            increasing_fillcolor="rgba(0,200,83,0.35)", decreasing_fillcolor="rgba(255,23,68,0.35)",
            name="Price",
        )
    )

    # SMA overlays
    if "sma_20" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["sma_20"], line=dict(color="#D4AF37", width=1.5),
                       name="SMA 20", opacity=0.85)
        )
    if "sma_50" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["sma_50"], line=dict(color="#7B68EE", width=1.5),
                       name="SMA 50", opacity=0.85)
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(26,26,46,0.5)",
        margin=dict(l=0, r=0, t=35, b=0),
        height=420,
        title=dict(text=f"{ticker} — Daily", font=dict(size=14, color="#D4AF37")),
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)", rangeslider_visible=False),
        yaxis=dict(gridcolor="rgba(255,255,255,0.04)", title="Price ($)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=10)),
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with col_signal:
    st.markdown("<div class='section-header'>🎯 Current Signal</div>", unsafe_allow_html=True)

    signal_result = None
    if DATA_AVAILABLE:
        try:
            strat = get_strategy(selected_strategy)
            signal_result = strat.generate_signal(df)
        except Exception:
            pass

    # Fallback demo signal
    if signal_result is None:
        class _DemoSignal:
            class _ST:
                BUY = "BUY"; SELL = "SELL"; HOLD = "HOLD"
                def __eq__(self, other): return self.name == other
                name = "BUY"
                value = "BUY"
            signal = type("S", (), {"name": "BUY", "value": "BUY"})()
            confidence = 0.74
            strategy = "MACD Crossover"
            explanation = ("MACD crossed above signal line with increasing volume. "
                           "RSI at 58 supports bullish momentum. SMA-20 trending above SMA-50.")
            indicators = {"rsi": 58.3, "macd": 1.24, "sma_20": 177.5, "sma_50": 174.2}
        signal_result = _DemoSignal()

    sig_name = signal_result.signal.name if hasattr(signal_result.signal, "name") else str(signal_result.signal)
    sig_name_upper = sig_name.upper()

    badge_class = "signal-hold"
    if "BUY" in sig_name_upper:
        badge_class = "signal-buy"
    elif "SELL" in sig_name_upper:
        badge_class = "signal-sell"

    st.markdown(
        f"<div style='text-align:center;margin:0.5rem 0 1rem;'>"
        f"<span class='signal-badge {badge_class}'>{sig_name_upper}</span></div>",
        unsafe_allow_html=True,
    )

    # Confidence
    conf = signal_result.confidence
    conf_pct = int(conf * 100) if conf <= 1 else int(conf)
    conf_color = "#00C853" if conf_pct >= 70 else "#D4AF37" if conf_pct >= 45 else "#FF1744"
    st.markdown(
        f"""<div style='margin-bottom:1rem;'>
            <div style='display:flex;justify-content:space-between;'>
                <span style='font-size:0.78rem;font-weight:600;color:#888;text-transform:uppercase;
                    letter-spacing:1px;'>Confidence</span>
                <span style='font-size:0.85rem;font-weight:700;color:{conf_color};
                    font-family:JetBrains Mono,monospace;'>{conf_pct}%</span>
            </div>
            <div class='confidence-bar-bg'>
                <div class='confidence-bar-fill' style='width:{conf_pct}%;
                    background:linear-gradient(90deg,{conf_color},rgba(255,255,255,0.15));'></div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Strategy
    st.markdown(
        f"<p style='font-size:0.78rem;color:#888;margin-bottom:0.15rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:1px;'>Strategy</p>"
        f"<p style='font-size:0.95rem;color:#E0E0E0;margin-bottom:0.8rem;'>"
        f"{signal_result.strategy}</p>",
        unsafe_allow_html=True,
    )

    # AI Explanation
    explanation = signal_result.explanation
    if AI_AVAILABLE:
        try:
            explanation = explain_signal(signal_result, df)
        except Exception:
            pass

    st.markdown(
        f"<p style='font-size:0.78rem;color:#888;margin-bottom:0.15rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:1px;'>AI Analysis</p>"
        f"<div class='glass-panel' style='font-size:0.85rem;line-height:1.65;'>{explanation}</div>",
        unsafe_allow_html=True,
    )

    # Key Indicators
    if hasattr(signal_result, "indicators") and signal_result.indicators:
        st.markdown(
            "<p style='font-size:0.78rem;color:#888;margin-bottom:0.3rem;font-weight:600;"
            "text-transform:uppercase;letter-spacing:1px;'>Key Indicators</p>",
            unsafe_allow_html=True,
        )
        ind_cols = st.columns(2)
        for i, (k, v) in enumerate(signal_result.indicators.items()):
            with ind_cols[i % 2]:
                val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
                st.markdown(
                    f"<div style='background:rgba(26,26,46,0.6);border:1px solid rgba(212,175,55,0.1);"
                    f"border-radius:8px;padding:0.4rem 0.6rem;margin-bottom:0.4rem;'>"
                    f"<span style='font-size:0.7rem;color:#888;text-transform:uppercase;'>{k}</span><br>"
                    f"<span style='font-size:0.95rem;font-weight:700;color:#E0E0E0;"
                    f"font-family:JetBrains Mono,monospace;'>{val_str}</span></div>",
                    unsafe_allow_html=True,
                )

    # Action Button
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    current_mode = st.session_state.trading_mode
    if st.session_state.kill_switch:
        st.error("🛑 Kill switch active — trading disabled")
    elif TRADING_AVAILABLE and isinstance(current_mode, TradingMode):
        if current_mode in (TradingMode.MANUAL, TradingMode.LIVE_MANUAL):
            if st.button(f"📋 View Signal Details", use_container_width=True):
                st.info(f"Signal: {sig_name_upper} | Confidence: {conf_pct}% | Strategy: {signal_result.strategy}")
        elif current_mode in (TradingMode.SEMI_AUTO, TradingMode.LIVE_SEMI_AUTO):
            if "BUY" in sig_name_upper or "SELL" in sig_name_upper:
                if st.button(f"✅ Approve & Execute {sig_name_upper}", use_container_width=True, type="primary"):
                    if executor:
                        try:
                            result = executor.execute_signal(
                                signal_result, ticker, quantity, current_mode
                            )
                            if result.success:
                                st.success(f"✅ {result.action_taken}: {result.message}")
                            else:
                                st.error(f"❌ {result.message}")
                        except Exception as e:
                            st.error(f"Execution error: {e}")
                    else:
                        st.warning("Executor not initialized")
            else:
                st.info("No actionable signal (HOLD)")
        elif current_mode in (TradingMode.AUTO_PAPER, TradingMode.LIVE_AUTO):
            st.info(f"🤖 {TRADING_MODE_LABELS.get(current_mode, 'Auto')} — signals execute automatically")
    else:
        if st.button("📋 View Signal Details", use_container_width=True):
            st.info(f"Signal: {sig_name_upper} | Confidence: {conf_pct}% | Strategy: {signal_result.strategy}")


st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── Risk Status ──────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>🛡️ Risk Management</div>", unsafe_allow_html=True)

risk_status = {}
if risk_manager:
    try:
        risk_status = risk_manager.get_risk_status()
    except Exception:
        pass

max_daily_loss = settings.MAX_DAILY_LOSS if settings else 1000
max_trades = settings.MAX_TRADES_PER_DAY if settings else 10
max_pos_size = settings.MAX_POSITION_SIZE if settings else 5000

daily_loss_used = abs(risk_status.get("daily_loss_used", abs(min(daily_pnl, 0))))
trades_used = risk_status.get("trades_today", 3)

rc1, rc2, rc3, rc4 = st.columns(4)

with rc1:
    pct_loss = min(daily_loss_used / max(max_daily_loss, 1), 1.0)
    bar_color = "#00C853" if pct_loss < 0.5 else "#D4AF37" if pct_loss < 0.8 else "#FF1744"
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Daily Loss Used</div>
            <div class='metric-value' style='font-size:1.3rem;'>{fmt_currency(daily_loss_used)}</div>
            <div class='metric-delta' style='color:{bar_color};'>
                of {fmt_currency(max_daily_loss)} limit ({pct_loss*100:.0f}%)
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

with rc2:
    pct_trades = min(trades_used / max(max_trades, 1), 1.0)
    bar_color2 = "#00C853" if pct_trades < 0.5 else "#D4AF37" if pct_trades < 0.8 else "#FF1744"
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Trades Today</div>
            <div class='metric-value' style='font-size:1.3rem;'>{trades_used} / {max_trades}</div>
            <div class='metric-delta' style='color:{bar_color2};'>
                {pct_trades*100:.0f}% used
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

with rc3:
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Max Position Size</div>
            <div class='metric-value' style='font-size:1.3rem;'>{fmt_currency(max_pos_size)}</div>
            <div class='metric-delta' style='color:var(--text-muted);'>Per-trade limit</div>
        </div>""",
        unsafe_allow_html=True,
    )

with rc4:
    ks_active = st.session_state.kill_switch
    ks_color = "#FF1744" if ks_active else "#00C853"
    ks_label = "ENGAGED" if ks_active else "DISENGAGED"
    ks_icon = "🛑" if ks_active else "✅"
    st.markdown(
        f"""<div class='metric-card'>
            <div class='metric-label'>Kill Switch</div>
            <div class='metric-value' style='font-size:1.3rem; color:{ks_color};'>
                {ks_icon} {ks_label}
            </div>
            <div class='metric-delta' style='color:var(--text-muted);'>Emergency brake</div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── Positions & Orders ───────────────────────────────────────────────────────
tab_pos, tab_orders = st.tabs(["📂 Open Positions", "📝 Recent Orders"])

with tab_pos:
    if positions_list:
        pos_df = pd.DataFrame(positions_list)
        display_cols = [c for c in ["symbol", "qty", "avg_entry_price", "current_price",
                                     "unrealized_pl", "market_value", "side"] if c in pos_df.columns]
        pos_df = pos_df[display_cols] if display_cols else pos_df

        def color_pnl(val):
            try:
                v = float(val)
                return "color: #00C853" if v >= 0 else "color: #FF1744"
            except Exception:
                return ""

        styled = pos_df.style
        if "unrealized_pl" in pos_df.columns:
            styled = styled.map(color_pnl, subset=["unrealized_pl"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")

with tab_orders:
    orders_list = []
    if broker:
        try:
            orders_list = broker.get_orders()
        except Exception:
            orders_list = get_demo_orders()
    else:
        orders_list = get_demo_orders()

    if orders_list:
        ord_df = pd.DataFrame(orders_list[:10])
        st.dataframe(ord_df, use_container_width=True, hide_index=True)
    else:
        st.info("No recent orders.")

# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class='disclaimer'>
        <strong>⚠️ Disclaimer:</strong> This AI Trading Assistant is for educational and informational
        purposes only. It does not constitute financial advice. Trading stocks involves risk of loss.
        Past performance does not guarantee future results. Always do your own research before making
        investment decisions. The developers are not responsible for any financial losses incurred
        through the use of this software.
    </div>
    """,
    unsafe_allow_html=True,
)

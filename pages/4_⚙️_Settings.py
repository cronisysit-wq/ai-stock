"""
Settings & Configuration Page
View and manage trading configuration, risk limits, safety controls,
broker info, and kill switch — all in one Wall Street–themed dashboard.
"""

import streamlit as st

st.set_page_config(
    page_title="Settings | AI Trading Assistant",
    page_icon="⚙️",
    layout="wide",
)

# ── Premium Wall Street Dark Theme CSS ────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
:root {
    --accent-gold: #D4AF37;
    --accent-cyan: #00E5FF;
    --profit-green: #00C853;
    --loss-red: #FF1744;
    --warning-amber: #FFA726;
    --glass-bg: rgba(26,26,46,0.72);
    --glass-border: rgba(212,175,55,0.12);
    --deep-bg: #0A0A1A;
}
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.stApp { background: var(--deep-bg); }

/* Section headers */
.section-header {
    font-size: 1.05rem; font-weight: 700; color: var(--accent-gold);
    text-transform: uppercase; letter-spacing: 1.6px;
    padding-bottom: 0.5rem; margin-bottom: 1rem;
    border-bottom: 1px solid rgba(212,175,55,0.18);
}

/* Card */
.card {
    background: var(--glass-bg); backdrop-filter: blur(14px);
    border: 1px solid var(--glass-border); border-radius: 14px;
    padding: 1.3rem 1.5rem; margin-bottom: 1rem;
}

/* Setting row */
.setting-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.65rem 0; border-bottom: 1px solid rgba(255,255,255,0.04);
}
.setting-row:last-child { border-bottom: none; }
.setting-key { font-size: 0.82rem; color: #888; font-weight: 600; }
.setting-value {
    font-size: 0.92rem; color: #E0E0E0; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

/* Badges */
.badge {
    display: inline-block; padding: 0.18rem 0.75rem; border-radius: 20px;
    font-size: 0.72rem; font-weight: 700; letter-spacing: 1px;
}
.badge-paper   { background: rgba(0,200,83,0.15);   color: #00C853; border: 1px solid #00C853; }
.badge-live    { background: rgba(255,23,68,0.15);   color: #FF1744; border: 1px solid #FF1744; }
.badge-enabled { background: rgba(212,175,55,0.15);  color: #D4AF37; border: 1px solid #D4AF37; }
.badge-disabled{ background: rgba(136,136,136,0.12); color: #888;    border: 1px solid #555; }
.badge-on      { background: rgba(0,229,255,0.12);   color: #00E5FF; border: 1px solid #00E5FF; }
.badge-off     { background: rgba(136,136,136,0.12); color: #888;    border: 1px solid #555; }
.badge-mock    { background: rgba(0,229,255,0.12);   color: #00E5FF; border: 1px solid #00E5FF; }
.badge-alpaca  { background: rgba(212,175,55,0.15);  color: #D4AF37; border: 1px solid #D4AF37; }

/* Progress bars */
.limit-bar-bg {
    background: rgba(255,255,255,0.06); border-radius: 8px;
    height: 10px; overflow: hidden; margin-top: 0.3rem;
}
.limit-bar-fill { height: 100%; border-radius: 8px; transition: width 0.3s ease; }

/* Dividers */
.gold-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #D4AF37, transparent);
    margin: 1.2rem 0; border: none;
}

/* Boxes */
.info-box {
    background: rgba(33,150,243,0.07); border: 1px solid rgba(33,150,243,0.25);
    border-radius: 12px; padding: 1rem 1.2rem; margin: 0.5rem 0;
}
.danger-box {
    background: rgba(255,23,68,0.06); border: 2px solid rgba(255,23,68,0.35);
    border-radius: 12px; padding: 1rem 1.2rem; margin: 0.5rem 0;
}
.warn-box {
    background: rgba(255,167,38,0.06); border: 2px solid rgba(255,167,38,0.3);
    border-radius: 12px; padding: 1rem 1.2rem; margin: 0.5rem 0;
}

/* Live trading banner */
.live-banner {
    background: linear-gradient(135deg, rgba(255,23,68,0.15), rgba(255,23,68,0.05));
    border: 2px solid #FF1744; border-radius: 14px;
    padding: 1.3rem 1.5rem; margin-bottom: 1.5rem;
    text-align: center; animation: pulse-border 2s ease-in-out infinite;
}
@keyframes pulse-border {
    0%, 100% { border-color: #FF1744; box-shadow: 0 0 8px rgba(255,23,68,0.25); }
    50%      { border-color: #FF6659; box-shadow: 0 0 20px rgba(255,23,68,0.45); }
}
.live-banner h2 {
    margin: 0; color: #FF1744; font-size: 1.35rem; font-weight: 900;
    letter-spacing: 1.5px;
}
.live-banner p {
    margin: 0.4rem 0 0; font-size: 0.85rem; color: #ccc;
}

/* Kill switch button styles */
.kill-btn-engage {
    background: linear-gradient(135deg, #FF1744, #D50000) !important;
    color: white !important; font-weight: 800 !important;
    border: 2px solid #FF1744 !important; border-radius: 12px !important;
    padding: 0.8rem 1rem !important; font-size: 1rem !important;
    letter-spacing: 1px !important;
}
.kill-btn-disengage {
    background: linear-gradient(135deg, #00C853, #009624) !important;
    color: white !important; font-weight: 800 !important;
    border: 2px solid #00C853 !important; border-radius: 12px !important;
    padding: 0.8rem 1rem !important; font-size: 1rem !important;
}

/* Kill switch status indicator */
.ks-status-engaged {
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.5rem 1rem; border-radius: 10px;
    background: rgba(255,23,68,0.12); border: 1px solid #FF1744;
    color: #FF1744; font-weight: 800; font-size: 1rem;
    animation: pulse-border 2s ease-in-out infinite;
}
.ks-status-clear {
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.5rem 1rem; border-radius: 10px;
    background: rgba(0,200,83,0.1); border: 1px solid #00C853;
    color: #00C853; font-weight: 700; font-size: 0.9rem;
}

/* Safety rules */
.rule-item {
    display: flex; gap: 0.7rem; padding: 0.55rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.rule-item:last-child { border-bottom: none; }
.rule-num {
    flex-shrink: 0; width: 1.8rem; height: 1.8rem;
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%; background: rgba(212,175,55,0.12);
    color: #D4AF37; font-weight: 800; font-size: 0.72rem;
    border: 1px solid rgba(212,175,55,0.25);
}
.rule-text { font-size: 0.82rem; color: #ccc; line-height: 1.5; }

/* Mode card */
.mode-row {
    display: flex; gap: 0.5rem; align-items: flex-start;
    padding: 0.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.04);
}
.mode-row:last-child { border-bottom: none; }
.mode-label {
    font-size: 0.82rem; font-weight: 700; color: #D4AF37; min-width: 120px;
}
.mode-desc { font-size: 0.78rem; color: #aaa; }
</style>
""", unsafe_allow_html=True)

# ── Module imports ────────────────────────────────────────────────────────────
try:
    from db.database import init_db
    init_db()
except Exception:
    pass

try:
    from config.settings import get_settings
    settings = get_settings()
    SETTINGS_OK = True
except Exception:
    settings = None
    SETTINGS_OK = False

try:
    from trading.risk_manager import RiskManager
    risk_manager = RiskManager()
    RISK_OK = True
except Exception:
    risk_manager = None
    RISK_OK = False

ROBINHOOD_AVAILABLE = False
try:
    from brokers.robinhood_watchlist import RobinhoodWatchlistBroker
    ROBINHOOD_AVAILABLE = True
except Exception:
    pass

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='margin-bottom:1.2rem;'>
  <h1 style='margin:0;font-size:2.1rem;font-weight:900;
      background:linear-gradient(135deg,#D4AF37,#F5E6A3);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
      ⚙️ Settings &amp; Configuration
  </h1>
  <p style='margin:0.3rem 0 0;color:#888;font-size:0.88rem;'>
      Trading configuration · Risk limits · Safety controls · Broker info
  </p>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE TRADING WARNING BANNER (full-width, above columns)
# ═══════════════════════════════════════════════════════════════════════════════
if settings and settings.ENABLE_LIVE_TRADING:
    st.markdown("""
    <div class='live-banner'>
      <h2>🚨 LIVE TRADING IS ENABLED — REAL MONEY AT RISK</h2>
      <p>
          All risk checks are active but real capital is exposed.
          To disable: set <code style='color:#FF6659;'>ENABLE_LIVE_TRADING=false</code> in your <code>.env</code> file and restart.
      </p>
    </div>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  BROKER SELECTION (full-width, above columns)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div class='section-header'>🏦 Broker Selection</div>", unsafe_allow_html=True)

st.markdown("""
<div style='background:rgba(255,167,38,0.06);border:1px solid rgba(255,167,38,0.2);
    border-left:4px solid #FFA726;border-radius:10px;padding:0.9rem 1.2rem;
    margin-bottom:1rem;font-size:0.85rem;color:#FFA726;'>
  ⚠️ <strong>Robinhood mode is watchlist/analysis only</strong> — no order execution.
  Robinhood does not provide an official public stock trading API.<br>
  <strong>Alpaca Live requires ENABLE_LIVE_TRADING=true in .env.</strong>
  Auto-trading is disabled by default.
</div>
""", unsafe_allow_html=True)

_broker_options = ["MockBroker (Default — No Keys Needed)"]
if SETTINGS_OK and settings:
    if settings.ALPACA_API_KEY:
        _broker_options.append("Alpaca Paper Trading")
        if settings.ENABLE_LIVE_TRADING:
            _broker_options.append("Alpaca Live ⚠️ (REAL MONEY)")
        else:
            _broker_options.append("Alpaca Live 🔒 (Set ENABLE_LIVE_TRADING=true)")
_broker_options.append("Robinhood Watchlist Only 🔍 (No Trading)")

_current_mode = st.session_state.get("broker_mode", _broker_options[0])
if _current_mode not in _broker_options:
    _current_mode = _broker_options[0]

bsc1, bsc2 = st.columns([2, 3])
with bsc1:
    selected_broker = st.selectbox(
        "Select Broker",
        options=_broker_options,
        index=_broker_options.index(_current_mode),
        key="broker_mode_selector",
        help="MockBroker: no keys needed. Alpaca Paper: requires API keys. Alpaca Live: ENABLE_LIVE_TRADING=true required. Robinhood: watchlist/analysis only.",
    )

with bsc2:
    _broker_caps = {
        "MockBroker (Default — No Keys Needed)": ("🟦 Mock", "Paper/mock only — no real money", "No API keys required", True),
        "Alpaca Paper Trading": ("🟨 Alpaca Paper", "Paper trading via official Alpaca API", "Requires ALPACA_API_KEY in .env", True),
        "Alpaca Live ⚠️ (REAL MONEY)": ("🟥 LIVE MONEY", "Real orders — real financial risk", "ENABLE_LIVE_TRADING=true required", True),
        "Alpaca Live 🔒 (Set ENABLE_LIVE_TRADING=true)": ("🔒 Locked", "Disabled until env var set", "Set ENABLE_LIVE_TRADING=true", False),
        "Robinhood Watchlist Only 🔍 (No Trading)": ("🔵 Watch Only", "Analysis only — no orders", "No credentials needed or stored", False),
    }
    cap = _broker_caps.get(selected_broker, ("❓", "Unknown", "Unknown", False))
    trade_str = "✅ Can execute orders" if cap[3] else "❌ Cannot execute orders"
    st.markdown(f"""
    <div class='card' style='padding:0.9rem 1.2rem;'>
        <div style='font-size:1rem;font-weight:800;margin-bottom:0.3rem;'>{cap[0]}</div>
        <div style='font-size:0.82rem;color:#aaa;margin-bottom:0.3rem;'>{cap[1]}</div>
        <div style='font-size:0.76rem;color:#666;margin-bottom:0.5rem;'>{cap[2]}</div>
        <div style='font-size:0.82rem;font-weight:700;'>{trade_str}</div>
    </div>
    """, unsafe_allow_html=True)

if st.button("💾 Apply Broker", key="apply_broker_btn"):
    st.session_state["broker_mode"] = selected_broker
    try:
        if "MockBroker" in selected_broker:
            from trading.mock_broker import MockBroker
            st.session_state["broker"] = MockBroker()
            st.success("✅ MockBroker activated — no real money involved.")
        elif "Alpaca Paper" in selected_broker:
            from trading.broker import AlpacaBroker
            st.session_state["broker"] = AlpacaBroker()
            st.success("✅ Alpaca Paper Trading activated.")
        elif "REAL MONEY" in selected_broker:
            if SETTINGS_OK and settings and settings.ENABLE_LIVE_TRADING:
                from trading.broker import AlpacaBroker
                st.session_state["broker"] = AlpacaBroker()
                st.error("⚠️ LIVE TRADING ACTIVE — real money at risk.")
            else:
                st.error("Cannot enable Alpaca Live — set ENABLE_LIVE_TRADING=true in .env first.")
        elif "Robinhood" in selected_broker:
            if ROBINHOOD_AVAILABLE:
                st.session_state["broker"] = RobinhoodWatchlistBroker()
                st.info("🔍 Robinhood Watchlist mode — analysis only, no orders.")
            else:
                st.error("Robinhood module unavailable.")
    except Exception as e:
        st.error(f"Broker init failed: {e}")

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  TWO-COLUMN LAYOUT
# ═══════════════════════════════════════════════════════════════════════════════
col_left, col_right = st.columns(2)


# ═══════════════════════════════════════════════════════════════════════════════
#  LEFT COLUMN
# ═══════════════════════════════════════════════════════════════════════════════
with col_left:

    # ── 1. TRADING MODE SECTION ───────────────────────────────────────────────
    st.markdown("<div class='section-header'>🏦 Trading Mode</div>", unsafe_allow_html=True)

    if settings:
        is_paper = settings.is_paper_trading
        is_live  = settings.ENABLE_LIVE_TRADING
        auto_en  = settings.ENABLE_AUTO_MODE
        auto_live_en = settings.ENABLE_AUTO_LIVE_TRADING

        # Determine current effective mode label
        if is_live and auto_live_en:
            effective_mode = "LIVE AUTO"
            effective_color = "#FF1744"
        elif is_live:
            effective_mode = "LIVE MANUAL"
            effective_color = "#FF1744"
        elif auto_en:
            effective_mode = "AUTO PAPER"
            effective_color = "#D4AF37"
        else:
            effective_mode = "PAPER MANUAL"
            effective_color = "#00C853"

        mode_badge  = "<span class='badge badge-paper'>PAPER</span>" if is_paper else "<span class='badge badge-live'>LIVE</span>"
        live_badge  = "<span class='badge badge-live'>ENABLED ⚠️</span>" if is_live else "<span class='badge badge-disabled'>DISABLED</span>"
        auto_badge  = "<span class='badge badge-enabled'>ENABLED</span>" if auto_en else "<span class='badge badge-disabled'>DISABLED</span>"
        auto_live_badge = "<span class='badge badge-live'>ENABLED ⚠️</span>" if auto_live_en else "<span class='badge badge-disabled'>DISABLED</span>"

        st.markdown(f"""
        <div class='card'>
          <div class='setting-row'>
            <span class='setting-key'>Effective Mode</span>
            <span style='color:{effective_color};font-weight:800;font-size:0.95rem;
                  font-family:"JetBrains Mono",monospace;'>{effective_mode}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Broker Environment</span>
            <span>{mode_badge}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>ENABLE_LIVE_TRADING</span>
            <span>{live_badge}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>ENABLE_AUTO_LIVE_TRADING</span>
            <span>{auto_live_badge}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>ENABLE_AUTO_MODE</span>
            <span>{auto_badge}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if is_live:
            st.markdown("""
            <div class='danger-box'>
              <p style='margin:0;font-weight:800;color:#FF1744;font-size:0.92rem;'>
                🔴 LIVE TRADING IS ACTIVE
              </p>
              <p style='margin:0.4rem 0 0;font-size:0.8rem;color:#ccc;'>
                Real money is at risk. Ensure all risk limits are properly configured.
                To disable, set <code>ENABLE_LIVE_TRADING=false</code> in your .env file.
              </p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='card'>
          <div style='text-align:center;padding:1rem;color:#888;'>
            <p>⚠️ Settings not loaded. Create a <code>.env</code> file from <code>.env.example</code>.</p>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── 2. API KEY STATUS ─────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>🔑 API Key Status</div>", unsafe_allow_html=True)

    def mask_key(key: str) -> str:
        if not key or len(key) < 8 or key.startswith("your_"):
            return "Not configured"
        return "••••••••••••" + key[-4:]

    if settings:
        api_key_masked = mask_key(settings.ALPACA_API_KEY)
        secret_masked  = mask_key(settings.ALPACA_SECRET_KEY)
        api_configured = settings.has_alpaca_keys
        use_mock       = settings.use_mock_broker

        key_status_color = "#00C853" if api_configured else "#FFA726"
        key_status_label = "✅ Configured — using AlpacaBroker" if api_configured else "📦 Not configured — using MockBroker"

        broker_badge = ("<span class='badge badge-alpaca'>AlpacaBroker</span>"
                        if not use_mock else
                        "<span class='badge badge-mock'>MockBroker</span>")

        st.markdown(f"""
        <div class='card'>
          <div class='setting-row'>
            <span class='setting-key'>API Key</span>
            <span class='setting-value'>{api_key_masked}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Secret Key</span>
            <span class='setting-value'>{secret_masked}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Broker</span>
            <span>{broker_badge}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Status</span>
            <span style='color:{key_status_color};font-weight:700;font-size:0.82rem;'>{key_status_label}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if not api_configured:
            st.markdown("""
            <div class='info-box'>
              <p style='margin:0;font-size:0.82rem;color:#ccc;'>
                📌 <strong>The app works fully without API keys</strong> using MockBroker.
                To connect to Alpaca:
                <ol style='margin:0.4rem 0 0;padding-left:1.2rem;line-height:1.8;'>
                  <li>Copy <code>.env.example</code> to <code>.env</code></li>
                  <li>Get free API keys from <a href='https://app.alpaca.markets' style='color:#D4AF37;'>alpaca.markets</a></li>
                  <li>Add keys to your <code>.env</code> file</li>
                  <li>Restart the app</li>
                </ol>
              </p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── 3. KILL SWITCH CONTROL ────────────────────────────────────────────────
    st.markdown("<div class='section-header'>🚨 Emergency Kill Switch</div>", unsafe_allow_html=True)

    # Sync kill switch state from risk_manager if available
    if "kill_switch_settings" not in st.session_state:
        if risk_manager:
            st.session_state.kill_switch_settings = risk_manager.kill_switch_engaged
        else:
            st.session_state.kill_switch_settings = False

    ks_active = st.session_state.kill_switch_settings

    # Status indicator
    if ks_active:
        st.markdown("""
        <div class='card' style='border-color:rgba(255,23,68,0.4);'>
          <div style='text-align:center;padding:0.5rem 0;'>
            <div class='ks-status-engaged'>
              🛑 KILL SWITCH ENGAGED — ALL TRADING HALTED
            </div>
          </div>
          <div style='margin-top:0.8rem;'>
            <p style='margin:0;font-size:0.82rem;color:#ccc;text-align:center;'>
              No new orders can be placed. Cancel open orders manually if needed.
            </p>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🔓 Disengage Kill Switch — Resume Trading", use_container_width=True):
            st.session_state.kill_switch_settings = False
            if risk_manager:
                try:
                    risk_manager.disengage_kill_switch()
                except Exception:
                    pass
            st.success("✅ Kill switch disengaged. Trading is now allowed.")
            st.rerun()
    else:
        st.markdown("""
        <div class='card' style='border-color:rgba(0,200,83,0.25);'>
          <div style='text-align:center;padding:0.5rem 0;'>
            <div class='ks-status-clear'>
              ✅ CLEAR — Trading Allowed
            </div>
          </div>
          <div style='margin-top:0.8rem;'>
            <p style='margin:0;font-size:0.8rem;color:#888;text-align:center;'>
              Press the button below to instantly halt all trading.
            </p>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🛑 ENGAGE EMERGENCY STOP", use_container_width=True, type="primary"):
            st.session_state.kill_switch_settings = True
            if risk_manager:
                try:
                    risk_manager.engage_kill_switch()
                except Exception:
                    pass
            st.error("⚠️ Kill switch ENGAGED. All trading is halted immediately.")
            st.rerun()

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── 4. BROKER INFO ────────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>🏛️ Broker Information</div>", unsafe_allow_html=True)

    if settings:
        use_mock  = settings.use_mock_broker
        is_paper  = settings.is_paper_trading
        base_url  = settings.ALPACA_BASE_URL

        broker_type   = "MockBroker (simulated)" if use_mock else "AlpacaBroker (real API)"
        broker_color  = "#00E5FF" if use_mock else "#D4AF37"
        env_label     = "Paper Trading" if is_paper else "Live Trading"
        env_color     = "#00C853" if is_paper else "#FF1744"
        env_badge     = "badge-paper" if is_paper else "badge-live"

        st.markdown(f"""
        <div class='card'>
          <div class='setting-row'>
            <span class='setting-key'>Broker Type</span>
            <span style='color:{broker_color};font-weight:700;font-size:0.85rem;'>{broker_type}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Base URL</span>
            <span class='setting-value' style='font-size:0.72rem;word-break:break-all;'>{base_url}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Environment</span>
            <span class='badge {env_badge}'>{env_label.upper()}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if use_mock:
            st.markdown("""
            <div class='info-box'>
              <p style='margin:0;font-size:0.8rem;color:#ccc;'>
                💡 <strong>MockBroker</strong> simulates order fills, account balances,
                and positions without connecting to any exchange.
                Perfect for development, testing, and learning.
              </p>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  RIGHT COLUMN
# ═══════════════════════════════════════════════════════════════════════════════
with col_right:

    # ── 5. RISK STATUS DASHBOARD ──────────────────────────────────────────────
    st.markdown("<div class='section-header'>🛡️ Risk Status Dashboard</div>", unsafe_allow_html=True)

    if settings:
        risk_status = {}
        if risk_manager:
            try:
                risk_status = risk_manager.get_risk_status()
            except Exception:
                pass

        daily_pnl      = risk_status.get("daily_pnl", 0) or 0
        trades_today   = risk_status.get("trades_today", 0) or 0
        ks_status_str  = risk_status.get("kill_switch_status", "OK")
        limits         = risk_status.get("limits", {})
        remaining      = risk_status.get("remaining", {})

        max_loss       = limits.get("max_daily_loss", settings.MAX_DAILY_LOSS)
        max_pos        = limits.get("max_position_size", settings.MAX_POSITION_SIZE)
        max_trades     = limits.get("max_trades_per_day", settings.MAX_TRADES_PER_DAY)
        stop_pct       = limits.get("stop_loss_pct", settings.STOP_LOSS_PCT)
        tp_pct         = limits.get("take_profit_pct", settings.TAKE_PROFIT_PCT)
        cooldown       = limits.get("cooldown_seconds", settings.COOLDOWN_SECONDS)
        rej_dup        = limits.get("reject_duplicate_orders", settings.REJECT_DUPLICATE_ORDERS)
        rej_mkt_closed = limits.get("reject_market_closed", settings.REJECT_MARKET_CLOSED)
        loss_capacity  = remaining.get("loss_capacity", max_loss)
        trades_remain  = remaining.get("trades_remaining", max_trades)

        # Percentages
        loss_used_pct  = min(100, abs(min(0, daily_pnl)) / max_loss * 100) if max_loss > 0 else 0
        trades_pct     = min(100, trades_today / max_trades * 100) if max_trades > 0 else 0

        loss_bar_color   = "#00C853" if loss_used_pct < 50 else "#FFA726" if loss_used_pct < 80 else "#FF1744"
        trades_bar_color = "#00C853" if trades_pct < 70 else "#FFA726" if trades_pct < 90 else "#FF1744"

        pnl_color = "#00C853" if daily_pnl >= 0 else "#FF1744"
        pnl_sign  = "+" if daily_pnl >= 0 else ""

        st.markdown(f"""
        <div class='card'>
          <!-- Daily P&L -->
          <div style='margin-bottom:1.1rem;'>
            <div class='setting-row'>
              <span class='setting-key'>Daily P&L</span>
              <span class='setting-value' style='color:{pnl_color};'>{pnl_sign}${daily_pnl:,.2f}</span>
            </div>
            <div class='setting-row' style='border-bottom:none;padding:0.2rem 0;'>
              <span style='font-size:0.72rem;color:#888;'>
                Loss used: ${abs(min(0,daily_pnl)):,.2f} / ${max_loss:,.2f}
              </span>
              <span style='font-size:0.72rem;color:{loss_bar_color};font-weight:700;'>{loss_used_pct:.0f}%</span>
            </div>
            <div class='limit-bar-bg'>
              <div class='limit-bar-fill' style='width:{loss_used_pct}%;background:{loss_bar_color};'></div>
            </div>
          </div>

          <!-- Trades today -->
          <div style='margin-bottom:1.1rem;'>
            <div class='setting-row'>
              <span class='setting-key'>Trades Today</span>
              <span class='setting-value'>{trades_today} / {max_trades}</span>
            </div>
            <div class='setting-row' style='border-bottom:none;padding:0.2rem 0;'>
              <span style='font-size:0.72rem;color:#888;'>
                Remaining: {trades_remain}
              </span>
              <span style='font-size:0.72rem;color:{trades_bar_color};font-weight:700;'>{trades_pct:.0f}%</span>
            </div>
            <div class='limit-bar-bg'>
              <div class='limit-bar-fill' style='width:{trades_pct}%;background:{trades_bar_color};'></div>
            </div>
          </div>

          <!-- Loss capacity remaining -->
          <div class='setting-row'>
            <span class='setting-key'>Loss Capacity Remaining</span>
            <span class='setting-value' style='color:{"#00C853" if loss_capacity > max_loss*0.3 else "#FFA726" if loss_capacity > max_loss*0.1 else "#FF1744"};'>${loss_capacity:,.2f}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Risk Limits Detail ────────────────────────────────────────────────
        st.markdown("<div class='section-header' style='margin-top:0.5rem;'>📊 Risk Limits</div>",
                    unsafe_allow_html=True)

        st.markdown(f"""
        <div class='card'>
          <div class='setting-row'>
            <span class='setting-key'>Max Daily Loss</span>
            <span class='setting-value'>${max_loss:,.2f}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Max Position Size</span>
            <span class='setting-value'>${max_pos:,.2f}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Max Trades / Day</span>
            <span class='setting-value'>{max_trades}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Stop Loss</span>
            <span class='setting-value' style='color:#FF1744;'>-{stop_pct:.1f}%</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Take Profit</span>
            <span class='setting-value' style='color:#00C853;'>+{tp_pct:.1f}%</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Cooldown After Loss</span>
            <span class='setting-value'>{cooldown}s ({cooldown//60}min)</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Order Safety ──────────────────────────────────────────────────────
        st.markdown("<div class='section-header' style='margin-top:0.5rem;'>🔒 Order Safety</div>",
                    unsafe_allow_html=True)

        dup_badge = ("<span class='badge badge-on'>ON</span>" if rej_dup
                     else "<span class='badge badge-off'>OFF</span>")
        mkt_badge = ("<span class='badge badge-on'>ON</span>" if rej_mkt_closed
                     else "<span class='badge badge-off'>OFF</span>")

        dup_window = getattr(settings, 'DUPLICATE_ORDER_WINDOW_SECONDS', 60)

        st.markdown(f"""
        <div class='card'>
          <div class='setting-row'>
            <span class='setting-key'>REJECT_DUPLICATE_ORDERS</span>
            <span>{dup_badge}</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>Duplicate Window</span>
            <span class='setting-value'>{dup_window}s</span>
          </div>
          <div class='setting-row'>
            <span class='setting-key'>REJECT_MARKET_CLOSED</span>
            <span>{mkt_badge}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    else:
        st.markdown("""<div class='card'>
            <p style='color:#888;text-align:center;'>Settings not available.</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── 6. SAFETY RULES DISPLAY ───────────────────────────────────────────────
    st.markdown("<div class='section-header'>🔐 12 Risk Checks (Mandatory Gate)</div>", unsafe_allow_html=True)

    risk_checks = [
        ("1", "Kill switch not engaged"),
        ("2", "Valid ticker symbol (non-empty, sane characters)"),
        ("3", "Quantity is strictly positive"),
        ("4", "Market data is available for the ticker"),
        ("5", "Market is open (live mode only, if REJECT_MARKET_CLOSED)"),
        ("6", "Daily loss limit not exceeded (MAX_DAILY_LOSS)"),
        ("7", "Position size within MAX_POSITION_SIZE"),
        ("8", "Max trades per day not exceeded (MAX_TRADES_PER_DAY)"),
        ("9", "Sufficient buying power in the account"),
        ("10", "Cooldown period after a losing trade (COOLDOWN_SECONDS)"),
        ("11", "Duplicate order prevention (same ticker+side within window)"),
        ("12", "AI override guard — AI signals cannot bypass any check"),
    ]

    rules_html = "<div class='card'>"
    for num, text in risk_checks:
        rules_html += f"""
        <div class='rule-item'>
          <div class='rule-num'>{num}</div>
          <div class='rule-text'>{text}</div>
        </div>"""
    rules_html += """
    <div style='margin-top:0.8rem;padding:0.7rem;border-radius:8px;
         background:rgba(212,175,55,0.06);border:1px solid rgba(212,175,55,0.15);'>
      <p style='margin:0;font-size:0.78rem;color:#D4AF37;font-weight:600;text-align:center;'>
        ⚠️ ALL 12 checks must pass. approve_trade() must return True before ANY broker call.
      </p>
    </div>
    </div>"""
    st.markdown(rules_html, unsafe_allow_html=True)

    st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

    # ── 6 Trading Modes ──────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>🎛️ 6 Trading Modes</div>", unsafe_allow_html=True)

    modes = [
        ("MANUAL", "Signals displayed only — NO orders placed. (Paper)"),
        ("SEMI_AUTO", "Signals queued for human approval before execution. (Paper)"),
        ("AUTO_PAPER", "Auto-executes on paper/mock. Requires ENABLE_AUTO_MODE=True."),
        ("LIVE_MANUAL", "Live-market signals displayed — no auto execution."),
        ("LIVE_SEMI_AUTO", "Live signals queued for human approval."),
        ("LIVE_AUTO", "Fully automated live trading. Requires BOTH ENABLE_LIVE_TRADING + ENABLE_AUTO_LIVE_TRADING."),
    ]

    modes_html = "<div class='card'>"
    for label, desc in modes:
        icon = "🟢" if "MANUAL" in label and "LIVE" not in label else (
            "🟡" if "SEMI" in label or "AUTO_PAPER" in label else "🔴"
        )
        modes_html += f"""
        <div class='mode-row'>
          <span class='mode-label'>{icon} {label}</span>
          <span class='mode-desc'>{desc}</span>
        </div>"""
    modes_html += "</div>"
    st.markdown(modes_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  FULL-WIDTH BOTTOM SECTIONS
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── AI Provider Status ────────────────────────────────────────────────────────
try:
    from ai.analyst import get_active_ai_provider, is_ai_available
    _ai_provider = get_active_ai_provider()
    _ai_ok = is_ai_available()
except Exception:
    _ai_provider = "rule-based"
    _ai_ok = False

_openai_key = settings.OPENAI_API_KEY if SETTINGS_OK and settings else ""
_gemini_key = settings.GEMINI_API_KEY if SETTINGS_OK and settings else ""
_ai_pref = settings.AI_PROVIDER if SETTINGS_OK and settings else "auto"
_openai_model = settings.OPENAI_MODEL if SETTINGS_OK and settings else "gpt-4o-mini"

_provider_badge = {
    "openai": ("badge-enabled", "OpenAI ChatGPT active"),
    "gemini": ("badge-on", "Google Gemini active"),
    "rule-based": ("badge-disabled", "Rule-based only — add OPENAI_API_KEY to .env"),
}.get(_ai_provider, ("badge-disabled", "Unknown"))

st.markdown("<div class='section-header'>🤖 AI Analysis Provider</div>", unsafe_allow_html=True)
st.markdown(f"""
<div class='card'>
  <div class='setting-row'>
    <span class='setting-key'>Active Provider</span>
    <span class='badge {_provider_badge[0]}'>{_provider_badge[1]}</span>
  </div>
  <div class='setting-row'>
    <span class='setting-key'>Preference (AI_PROVIDER)</span>
    <span class='setting-value'>{_ai_pref}</span>
  </div>
  <div class='setting-row'>
    <span class='setting-key'>OpenAI Key</span>
    <span class='setting-value'>{'✅ Configured' if _openai_key else '❌ Not set'}</span>
  </div>
  <div class='setting-row'>
    <span class='setting-key'>OpenAI Model</span>
    <span class='setting-value'>{_openai_model}</span>
  </div>
  <div class='setting-row'>
    <span class='setting-key'>Gemini Key (fallback)</span>
    <span class='setting-value'>{'✅ Configured' if _gemini_key else '❌ Not set'}</span>
  </div>
</div>
""", unsafe_allow_html=True)

if not _ai_ok:
    st.info(
        "Add **OPENAI_API_KEY** to your `.env` file (copy from `.env.example`), then restart the app. "
        "OpenAI is used first; Gemini is optional fallback when `AI_PROVIDER=auto`."
    )

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── AI Restriction Notice ─────────────────────────────────────────────────────
st.markdown("""
<div style='background:rgba(212,175,55,0.05);border:1px solid rgba(212,175,55,0.2);
    border-radius:12px;padding:1.1rem 1.5rem;margin-bottom:1.2rem;text-align:center;'>
  <p style='margin:0;font-size:0.95rem;font-weight:700;color:#D4AF37;'>
    🤖 AI Can Explain Signals Only
  </p>
  <p style='margin:0.4rem 0 0;font-size:0.82rem;color:#aaa;max-width:700px;margin-left:auto;margin-right:auto;'>
    The AI analyst can explain market signals and provide educational context.
    It <strong>cannot</strong> place orders, modify risk limits, or override any safety rule.
    All trade decisions are gated by the 12-check risk manager — its verdict is final.
  </p>
</div>
""", unsafe_allow_html=True)

# ── 7. CONFIGURATION INSTRUCTIONS ────────────────────────────────────────────
st.markdown("<div class='section-header'>📝 Configuration Instructions</div>", unsafe_allow_html=True)

col_cfg_left, col_cfg_right = st.columns(2)

with col_cfg_left:
    st.markdown("""
    <div class='info-box'>
      <p style='margin:0;font-size:0.85rem;color:#ccc;line-height:1.8;'>
        All settings are managed via the <code style='color:#D4AF37;'>.env</code> file in the project root.
        To change settings:
        <ol style='margin:0.5rem 0 0;padding-left:1.2rem;'>
          <li>Open <code>.env</code> (copy from <code>.env.example</code> if missing)</li>
          <li>Edit the relevant values</li>
          <li>Restart the Streamlit app for changes to take effect</li>
        </ol>
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.code("""# .env configuration file
# ── API Keys ──
OPENAI_API_KEY=sk-your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
GEMINI_API_KEY=your_gemini_key_here
AI_PROVIDER=auto

ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# ── Safety Locks ──
ENABLE_LIVE_TRADING=false
ENABLE_AUTO_LIVE_TRADING=false
ENABLE_AUTO_MODE=false

# ── Risk Limits ──
MAX_DAILY_LOSS=100
MAX_POSITION_SIZE=500
MAX_TRADES_PER_DAY=5
STOP_LOSS_PCT=2.0
TAKE_PROFIT_PCT=5.0
COOLDOWN_SECONDS=300

# ── Order Safety ──
REJECT_DUPLICATE_ORDERS=true
DUPLICATE_ORDER_WINDOW_SECONDS=60
REJECT_MARKET_CLOSED=true""", language="ini")

with col_cfg_right:
    st.markdown("""
    <div class='danger-box'>
      <p style='margin:0;font-weight:800;color:#FF1744;font-size:0.9rem;'>
        ⚠️ Warning: Enabling Live Trading
      </p>
      <p style='margin:0.5rem 0 0;font-size:0.82rem;color:#ccc;line-height:1.8;'>
        Setting <code>ENABLE_LIVE_TRADING=true</code> will allow the app to
        place <strong>real orders with real money</strong> through your Alpaca account.
        <br><br>
        <strong>Before enabling:</strong>
        <ul style='margin:0.3rem 0 0;padding-left:1.2rem;'>
          <li>Ensure all risk limits are configured correctly</li>
          <li>Start with a paper trading account first</li>
          <li>Test thoroughly with MockBroker</li>
          <li>Never trade with money you cannot afford to lose</li>
          <li>The kill switch is your last line of defence</li>
        </ul>
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='warn-box'>
      <p style='margin:0;font-weight:700;color:#FFA726;font-size:0.85rem;'>
        🔒 LIVE_AUTO requires TWO flags
      </p>
      <p style='margin:0.4rem 0 0;font-size:0.8rem;color:#ccc;line-height:1.7;'>
        Fully automated live trading requires both:
        <br>• <code>ENABLE_LIVE_TRADING=true</code>
        <br>• <code>ENABLE_AUTO_LIVE_TRADING=true</code>
        <br><br>
        Setting only one flag will NOT enable auto-live. This is a deliberate
        two-key safety mechanism.
      </p>
    </div>
    """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='font-size:0.72rem;color:#555;text-align:center;line-height:1.7;padding-bottom:1rem;'>
  ⚠️ This application is an educational AI trading assistant. It is NOT financial advice.
  Never trade with money you cannot afford to lose. Always consult a qualified financial advisor.
  <br>All settings are read-only in the UI — modify them via the <code>.env</code> file only.
</div>
""", unsafe_allow_html=True)

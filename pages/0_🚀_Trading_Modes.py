"""
Trading Modes Hub — Day Trading Agent + Monthly Income.

Day Trading Agent: scans US market, R-multiple sizing, auto exit rules.
Targets scale with account (% of equity) — $100–200 is just a reference on small accounts.

NOT FINANCIAL ADVICE.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time as _time

st.set_page_config(
    page_title="Trading Modes | AI Trading Assistant",
    page_icon="🚀",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--gold:#D4AF37;--cyan:#00E5FF;--green:#00C853;--red:#FF1744;--bg:#06060F;}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:var(--bg);}
.hero{background:linear-gradient(135deg,rgba(212,175,55,0.1),rgba(0,229,255,0.06));
  border:1px solid rgba(212,175,55,0.22);border-radius:16px;padding:1.5rem 2rem;margin-bottom:1rem;}
.hero h1{margin:0;font-size:2rem;font-weight:900;
  background:linear-gradient(135deg,#D4AF37,#00E5FF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.mode-card{background:rgba(18,18,38,0.85);border:1px solid rgba(212,175,55,0.15);
  border-radius:14px;padding:1.2rem;margin-bottom:0.8rem;}
.mode-active{border-color:#D4AF37;box-shadow:0 0 24px rgba(212,175,55,0.12);}
.disc{background:rgba(255,167,38,0.06);border-left:4px solid #FFA726;border-radius:8px;
  padding:0.75rem 1rem;margin:1rem 0;color:#FFA726;font-size:0.82rem;font-weight:600;}
.sh{font-size:0.88rem;font-weight:800;color:#D4AF37;text-transform:uppercase;
  letter-spacing:2px;border-bottom:1px solid rgba(212,175,55,0.15);padding-bottom:0.4rem;margin-bottom:0.8rem;}
.mc{background:rgba(212,175,55,0.05);border:1px solid rgba(212,175,55,0.12);
  border-radius:10px;padding:0.7rem;text-align:center;}
.ml{font-size:0.62rem;color:#666;text-transform:uppercase;letter-spacing:1px;}
.mv{font-size:1.4rem;font-weight:900;color:#fff;font-family:'JetBrains Mono',monospace;}
.gd{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);margin:1.2rem 0;}
.news-bull{background:rgba(0,200,83,0.08);border-left:3px solid #00C853;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
.news-bear{background:rgba(255,23,68,0.08);border-left:3px solid #FF1744;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
.news-neut{background:rgba(150,150,150,0.06);border-left:3px solid #888;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
.ai-banner-openai{background:linear-gradient(135deg,rgba(116,185,255,0.12),rgba(0,200,83,0.08));
  border:1px solid rgba(0,200,83,0.35);border-radius:12px;padding:0.9rem 1.2rem;margin-bottom:1rem;}
.ai-banner-gemini{background:linear-gradient(135deg,rgba(66,133,244,0.1),rgba(212,175,55,0.06));
  border:1px solid rgba(66,133,244,0.35);border-radius:12px;padding:0.9rem 1.2rem;margin-bottom:1rem;}
.ai-banner-off{background:rgba(136,136,136,0.08);border:1px solid rgba(136,136,136,0.25);
  border-radius:12px;padding:0.9rem 1.2rem;margin-bottom:1rem;}
.threshold-card{background:rgba(0,229,255,0.04);border:1px solid rgba(0,229,255,0.18);
  border-radius:12px;padding:1rem 1.2rem;margin:0.6rem 0;}
</style>
""", unsafe_allow_html=True)

# ── Init ───────────────────────────────────────────────────────────────────────
try:
    from db.database import init_db
    from config.settings import get_settings
    init_db()
    settings = get_settings()
    SETTINGS_OK = True
except Exception:
    settings = None
    SETTINGS_OK = False

ENGINE_OK = False
try:
    from trading.mode_engine import (
        TradingModeEngine, TradingStyle, ExecutionPreference,
        TRADING_STYLE_LABELS, EXECUTION_LABELS,
    )
    from trading.day_trading_agent import (
        get_session_phase, scale_targets_for_equity, SessionPhase,
        resolve_day_trading_thresholds,
    )
    from ai.institutional_advisor import (
        AdvisorPersona, PERSONA_LABELS, DAILY_TARGET_PRESETS,
        scale_target_table, explain_integrated, explain_batch_summary,
    )
    ADVISOR_OK = True
    ENGINE_OK = True
except Exception as e:
    ADVISOR_OK = False
    st.error(f"Mode engine: {e}")

QUEUE_OK = False
try:
    from trading.approval_queue import ApprovalQueue, STATUS_PENDING, STATUS_APPROVED, STATUS_EXECUTED
    QUEUE_OK = True
except Exception:
    pass

for key, default in {
    "tm_style": TradingStyle.DAY_TRADING if ENGINE_OK else "day_trading",
    "tm_exec": ExecutionPreference.MANUAL if ENGINE_OK else "manual",
    "tm_scan_result": None,
    "tm_daily_target": 150.0,
    "tm_daily_target_pct": 0.75,
    "tm_use_usd_floor": False,
    "tm_account_equity": 25000.0,
    "tm_agent_cycle": None,
    "tm_agent_advice": None,
    "tm_advisor_persona": AdvisorPersona.BUFFETT if ENGINE_OK else "warren_buffett",
    "tm_target_preset": "Conservative 0.75%",
    "approval_queue": None,
    "broker": None,
    "risk_manager": None,
    "executor": None,
    "kill_switch": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state["approval_queue"] is None and QUEUE_OK:
    st.session_state["approval_queue"] = ApprovalQueue()

if st.session_state["broker"] is None:
    try:
        from config.settings import get_settings as gs
        s = gs()
        if s.use_mock_broker:
            from trading.mock_broker import MockBroker
            st.session_state["broker"] = MockBroker()
        else:
            from trading.broker import AlpacaBroker
            st.session_state["broker"] = AlpacaBroker()
    except Exception:
        try:
            from trading.mock_broker import MockBroker
            st.session_state["broker"] = MockBroker()
        except Exception:
            pass

if st.session_state["risk_manager"] is None:
    try:
        from trading.risk_manager import RiskManager
        st.session_state["risk_manager"] = RiskManager()
    except Exception:
        pass

if st.session_state["executor"] is None and st.session_state["broker"] and st.session_state["risk_manager"]:
    try:
        from trading.executor import TradeExecutor
        st.session_state["executor"] = TradeExecutor(
            st.session_state["broker"], st.session_state["risk_manager"]
        )
    except Exception:
        pass

broker = st.session_state.get("broker")
is_mock = broker and hasattr(broker, "_initial_capital")
is_live = SETTINGS_OK and settings and settings.ENABLE_LIVE_TRADING

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🚀 Trading Modes</h1>
  <p style="color:#888;margin:0.4rem 0 0;font-size:0.9rem;">
    Two strategies · Manual or Auto · US market scan · Paper trading by default
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="disc">
  ⚠️ <strong>NOT FINANCIAL ADVICE.</strong> Profit targets scale with your account 
  (e.g. 0.75% daily on $25k ≈ $187, on $100k ≈ $750). $100–200 is only a reference 
  for smaller accounts — not a guarantee. Auto mode uses paper/mock unless live flags are set.
</div>
""", unsafe_allow_html=True)

if is_live:
    st.error("🚨 LIVE TRADING ENABLED — real money at risk")
if st.session_state.get("kill_switch"):
    st.error("🛑 Kill switch ACTIVE — all trading halted")

# ── AI provider status ────────────────────────────────────────────────────────
try:
    from ai.analyst import get_active_ai_provider, is_ai_available
    _ai_provider = get_active_ai_provider()
    _ai_live = is_ai_available()
except Exception:
    _ai_provider = "rule-based"
    _ai_live = False

if _ai_provider == "openai":
    st.markdown("""
    <div class="ai-banner-openai">
      <strong style="color:#00C853;font-size:0.95rem;">🤖 OpenAI ChatGPT — Active</strong>
      <p style="margin:0.35rem 0 0;color:#aaa;font-size:0.82rem;">
        Institutional personas, scan summaries, and research notes use OpenAI.
        AI explains only — it cannot place orders or override risk gates.
      </p>
    </div>
    """, unsafe_allow_html=True)
elif _ai_provider == "gemini":
    st.markdown("""
    <div class="ai-banner-gemini">
      <strong style="color:#4285F4;font-size:0.95rem;">🤖 Google Gemini — Active</strong>
      <p style="margin:0.35rem 0 0;color:#aaa;font-size:0.82rem;">
        AI analysis is live via Gemini. Add <code>OPENAI_API_KEY</code> to .env for ChatGPT (preferred).
      </p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="ai-banner-off">
      <strong style="color:#888;font-size:0.95rem;">📊 Rule-Based Mode — No AI Key</strong>
      <p style="margin:0.35rem 0 0;color:#666;font-size:0.82rem;">
        Add <code>OPENAI_API_KEY</code> to your <code>.env</code> file for ChatGPT-powered advisor notes.
        Restart the app after saving. See <strong>Settings → AI Analysis Provider</strong>.
      </p>
    </div>
    """, unsafe_allow_html=True)

# ── Mode selection ─────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>1 · Choose Your Strategy</div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)

with c1:
    day_sel = st.session_state["tm_style"] == TradingStyle.DAY_TRADING if ENGINE_OK else True
    st.markdown(
        f"<div class='mode-card {'mode-active' if day_sel else ''}'>"
        "<strong style='color:#FFA726;font-size:1.1rem;'>🔥 Day Trading Agent</strong><br>"
        "<span style='color:#888;font-size:0.85rem;'>"
        "Scans 150+ US stocks · ATR/R-multiple sizing · Stop/target/EOD exits · "
        "Targets scale with account size</span></div>",
        unsafe_allow_html=True,
    )
    if st.button("Select Day Trading", use_container_width=True, type="primary" if day_sel else "secondary"):
        st.session_state["tm_style"] = TradingStyle.DAY_TRADING
        st.session_state["tm_scan_result"] = None
        st.rerun()

with c2:
    inc_sel = st.session_state["tm_style"] == TradingStyle.MONTHLY_INCOME if ENGINE_OK else False
    st.markdown(
        f"<div class='mode-card {'mode-active' if inc_sel else ''}'>"
        "<strong style='color:#00C853;font-size:1.1rem;'>💰 Monthly Income / Swing</strong><br>"
        "<span style='color:#888;font-size:0.85rem;'>"
        "Scans S&P 500 quality names · Trend + lower risk · "
        "Swing holds · Est. daily $ toward your target</span></div>",
        unsafe_allow_html=True,
    )
    if st.button("Select Monthly Income", use_container_width=True, type="primary" if inc_sel else "secondary"):
        st.session_state["tm_style"] = TradingStyle.MONTHLY_INCOME
        st.session_state["tm_scan_result"] = None
        st.rerun()

style: TradingStyle = st.session_state["tm_style"]

# ── Execution mode ─────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>2 · Manual or Auto</div>", unsafe_allow_html=True)

e1, e2 = st.columns(2)
with e1:
    man_sel = st.session_state["tm_exec"] == ExecutionPreference.MANUAL
    st.markdown(
        f"<div class='mode-card {'mode-active' if man_sel else ''}'>"
        "<strong>👤 Manual</strong> — Scan → you pick → approve → execute</div>",
        unsafe_allow_html=True,
    )
    if st.button("Manual Mode", use_container_width=True, type="primary" if man_sel else "secondary"):
        st.session_state["tm_exec"] = ExecutionPreference.MANUAL
        st.rerun()
with e2:
    auto_sel = st.session_state["tm_exec"] == ExecutionPreference.AUTO
    auto_ok = SETTINGS_OK and settings and settings.ENABLE_AUTO_MODE
    st.markdown(
        f"<div class='mode-card {'mode-active' if auto_sel else ''}'>"
        f"<strong>🤖 Auto</strong> — Scan → top BUY picks auto-execute (paper)"
        f"{' · <span style=\"color:#00C853\">enabled</span>' if auto_ok else ' · <span style=\"color:#FF1744\">set ENABLE_AUTO_MODE=true</span>'}"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button("Auto Mode", use_container_width=True, type="primary" if auto_sel else "secondary"):
        st.session_state["tm_exec"] = ExecutionPreference.AUTO
        st.rerun()

exec_pref: ExecutionPreference = st.session_state["tm_exec"]

# Day Trading Agent session bar
if style == TradingStyle.DAY_TRADING and ENGINE_OK:
    phase = get_session_phase()
    phase_colors = {
        SessionPhase.OPEN: "#00C853", SessionPhase.POWER_HOUR: "#FFA726",
        SessionPhase.MIDDAY: "#00E5FF", SessionPhase.PRE_MARKET: "#D4AF37",
        SessionPhase.CLOSED: "#888",
    }
    eq = st.session_state["tm_account_equity"]
    tgt_pct = st.session_state.get("tm_daily_target_pct", 0.75)
    usd_floor = st.session_state["tm_daily_target"] if st.session_state.get("tm_use_usd_floor") else None
    scaled = scale_targets_for_equity(eq, tgt_pct, usd_floor)
    st.markdown(
        f"<div style='display:flex;gap:1.5rem;flex-wrap:wrap;padding:0.6rem 0;color:#888;font-size:0.85rem;'>"
        f"<span>Session: <strong style='color:{phase_colors.get(phase,'#888')}'>{phase.value.replace('_',' ').upper()}</strong></span>"
        f"<span>Equity: <strong style='color:#fff;'>${eq:,.0f}</strong></span>"
        f"<span>Daily target: <strong style='color:#00C853;'>${scaled['effective_daily_target']:,.0f}</strong> "
        f"({tgt_pct}%)</span>"
        f"<span>Risk/trade: <strong style='color:#FFA726;'>${scaled['risk_per_trade_usd']:,.0f}</strong></span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if tgt_pct >= 5:
        st.warning(
            f"⚠️ **{tgt_pct}% daily target** (≈ ${scaled['effective_daily_target']:,.0f}) is very aggressive. "
            f"Professional traders rarely target >1–2%/day sustainably."
        )
    with st.expander("📈 Target scaling table (same % → any account size)"):
        st.dataframe(pd.DataFrame(scale_target_table(eq)), hide_index=True, use_container_width=True)

st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

# ── AI Advisor persona ────────────────────────────────────────────────────────
if ADVISOR_OK:
    st.markdown("<div class='sh'>3 · AI Institutional Advisor + News/Sentiment</div>", unsafe_allow_html=True)
    persona_keys = list(PERSONA_LABELS.keys())
    current_persona = st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT)
    if current_persona not in persona_keys:
        current_persona = AdvisorPersona.BUFFETT
    p_idx = persona_keys.index(current_persona)
    pc1, pc2 = st.columns([2, 2])
    with pc1:
        sel_p = st.selectbox(
            "Advisor persona (educational simulation)",
            range(len(persona_keys)),
            format_func=lambda i: PERSONA_LABELS[persona_keys[i]],
            index=p_idx,
        )
        st.session_state["tm_advisor_persona"] = persona_keys[sel_p]
    with pc2:
        st.caption(
            "Integrates **Yahoo news**, **headline sentiment**, **analyst consensus**, "
            "and **technicals** into composite ranking. Not real advice from these firms."
        )

st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

# ── Scan controls ──────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>4 · Scan & Target Settings</div>", unsafe_allow_html=True)

if not ENGINE_OK:
    st.stop()

presets = TradingModeEngine.presets_for_style(style)
preset_labels = list(presets.keys())
preset_vals = list(presets.values())
default_preset = TradingModeEngine.default_preset(style)
default_idx = preset_vals.index(default_preset) if default_preset in preset_vals else 0

sc1, sc2, sc3, sc4 = st.columns(4)
with sc1:
    preset_idx = st.selectbox("Universe", range(len(preset_labels)),
                              format_func=lambda i: preset_labels[i], index=default_idx)
    selected_preset = preset_vals[preset_idx]
with sc2:
    top_n = st.slider("Top results", 10, 50, 25, 5)
with sc3:
    st.session_state["tm_account_equity"] = st.number_input(
        "Account size ($)", min_value=1000.0, value=float(st.session_state["tm_account_equity"]),
        step=1000.0,
    )
with sc4:
    if style == TradingStyle.MONTHLY_INCOME:
        preset_names = list(DAILY_TARGET_PRESETS.keys()) if ADVISOR_OK else ["Custom"]
        preset_choice = st.selectbox("Daily target preset", preset_names, key="inc_target_preset")
        if ADVISOR_OK and DAILY_TARGET_PRESETS.get(preset_choice, -1) > 0:
            st.session_state["tm_daily_target_pct"] = DAILY_TARGET_PRESETS[preset_choice]
        st.session_state["tm_daily_target"] = st.number_input(
            "Daily $ target (est.)", min_value=50.0, max_value=5000000.0,
            value=float(st.session_state["tm_daily_target"]), step=100.0,
        )
    else:
        if ADVISOR_OK:
            preset_names = list(DAILY_TARGET_PRESETS.keys())
            cur = st.session_state.get("tm_target_preset", "Conservative 0.75%")
            p_i = preset_names.index(cur) if cur in preset_names else 0
            chosen = st.selectbox("Daily target preset", preset_names, index=p_i, key="day_target_preset")
            st.session_state["tm_target_preset"] = chosen
            if DAILY_TARGET_PRESETS[chosen] > 0:
                st.session_state["tm_daily_target_pct"] = DAILY_TARGET_PRESETS[chosen]
        st.session_state["tm_daily_target_pct"] = st.number_input(
            "Daily target (% equity)", min_value=0.25, max_value=25.0,
            value=float(st.session_state.get("tm_daily_target_pct", 0.75)), step=0.25,
            format="%.2f",
            help="Scales with account: 3% on $50k = $1,500/day reference",
        )

if style == TradingStyle.DAY_TRADING:
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.session_state["tm_use_usd_floor"] = st.checkbox(
            "USD floor (optional)", value=st.session_state.get("tm_use_usd_floor", False),
            help="Use max(% target, $ floor) — e.g. $100 min on small accounts",
        )
    with dc2:
        if st.session_state["tm_use_usd_floor"]:
            st.session_state["tm_daily_target"] = st.number_input(
                "USD floor ($)", min_value=50.0, max_value=100000.0,
                value=float(st.session_state["tm_daily_target"]), step=50.0,
            )
    with dc3:
        if SETTINGS_OK and settings:
            st.caption(
                f"Agent: max {settings.DAY_TRADE_MAX_OPEN_POSITIONS} positions · "
                f"{settings.DAY_TRADE_RISK_REWARD:.0f}:1 R:R · "
                f"flat {settings.DAY_TRADE_FLAT_BEFORE_CLOSE_MIN}m before close"
            )

    _target_pct = float(st.session_state.get("tm_daily_target_pct", 0.75))
    _profile = resolve_day_trading_thresholds(_target_pct)
    st.session_state["tm_threshold_profile"] = _profile

    st.markdown(f"""
    <div class="threshold-card">
      <strong style="color:#00E5FF;font-size:0.88rem;text-transform:uppercase;letter-spacing:1px;">
        ⚙️ Agent Profile: {_profile.label} ({_profile.aggressiveness})
      </strong>
      <p style="margin:0.4rem 0 0.6rem;color:#888;font-size:0.8rem;">{_profile.notes}</p>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;font-size:0.78rem;">
        <div><span style="color:#666;">Min score</span><br><strong style="color:#fff;">{_profile.min_setup_score:.0f}</strong></div>
        <div><span style="color:#666;">Auto composite</span><br><strong style="color:#fff;">{_profile.min_composite_auto:.0f}</strong></div>
        <div><span style="color:#666;">Min sentiment</span><br><strong style="color:#fff;">{_profile.min_sentiment_score:.0f}</strong></div>
        <div><span style="color:#666;">Max trades/day</span><br><strong style="color:#fff;">{_profile.max_trades_per_day}</strong></div>
        <div><span style="color:#666;">Risk/trade</span><br><strong style="color:#fff;">{_profile.risk_per_trade_pct:.2f}%</strong></div>
        <div><span style="color:#666;">Max loss/day</span><br><strong style="color:#fff;">{_profile.daily_max_loss_pct:.1f}%</strong></div>
        <div><span style="color:#666;">Loss cooldown</span><br><strong style="color:#fff;">{_profile.loss_cooldown_minutes}m</strong></div>
        <div><span style="color:#666;">Trail stop</span><br><strong style="color:#fff;">{_profile.trailing_stop_pct:.1f}%</strong></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

if broker:
    try:
        acct = broker.get_account()
        st.session_state["tm_account_equity"] = float(acct.get("equity", st.session_state["tm_account_equity"]))
    except Exception:
        pass

auto_max = 3
_profile_for_slider = st.session_state.get("tm_threshold_profile")
if _profile_for_slider is None and ENGINE_OK:
    _profile_for_slider = resolve_day_trading_thresholds(
        float(st.session_state.get("tm_daily_target_pct", 0.75))
    )
auto_min_score = _profile_for_slider.min_setup_score if _profile_for_slider else 68.0
if exec_pref == ExecutionPreference.AUTO:
    ac1, ac2 = st.columns(2)
    with ac1:
        auto_max = st.number_input(
            "Max entries per cycle", 1, 5, min(3, _profile_for_slider.max_open_positions if _profile_for_slider else 3),
        )
    with ac2:
        auto_min_score = st.slider(
            "Min setup score (override)",
            55.0, 90.0,
            float(_profile_for_slider.min_setup_score if _profile_for_slider else 68.0),
            1.0,
            help="Preset profile sets the default; raise to be more selective.",
        )

btn_label = "🤖 RUN DAY AGENT" if style == TradingStyle.DAY_TRADING else "🔍 SCAN US MARKET"
scan_btn = st.button(btn_label, type="primary", use_container_width=True)

engine = TradingModeEngine(
    broker=broker,
    risk_manager=st.session_state.get("risk_manager"),
    executor=st.session_state.get("executor"),
)

if scan_btn:
    progress = st.progress(0, text="Starting...")
    def _cb(done, total):
        progress.progress(done / max(total, 1), text=f"Scanning {done}/{total}...")

    equity = st.session_state["tm_account_equity"]
    usd_floor = st.session_state["tm_daily_target"] if (
        style == TradingStyle.DAY_TRADING and st.session_state.get("tm_use_usd_floor")
    ) else None

    with st.spinner("Agent running..." if style == TradingStyle.DAY_TRADING else "Scanning..."):
        try:
            t0 = _time.time()

            if style == TradingStyle.DAY_TRADING:
                cycle = engine.run_day_agent(
                    auto=(exec_pref == ExecutionPreference.AUTO),
                    account_equity=equity,
                    preset=selected_preset,
                    kill_switch=st.session_state.get("kill_switch", False),
                    progress_callback=_cb,
                    daily_profit_target_pct=st.session_state.get("tm_daily_target_pct", 0.75),
                    daily_profit_target_usd=usd_floor,
                    top_n=top_n,
                    min_setup_score=auto_min_score,
                    advisor_persona=st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT).value
                    if ADVISOR_OK else "warren_buffett",
                    enable_sentiment=True,
                )
                st.session_state["tm_agent_cycle"] = cycle

                from trading.mode_engine import CandidatePick
                candidates = []
                for i, setup in enumerate(cycle.setups, start=1):
                    sz = setup.sizing
                    candidates.append(CandidatePick(
                        ticker=setup.ticker, rank=i, price=setup.price,
                        signal=setup.signal, score=setup.composite_score or setup.score,
                        quantity=float(sz.shares), stop_loss=sz.stop_loss,
                        take_profit=sz.take_profit, explanation=setup.explanation,
                        est_daily_usd=sz.reward_usd, source="day_agent", raw=setup,
                    ))
                result = __import__("trading.mode_engine", fromlist=["ModeScanResult"]).ModeScanResult(
                    style=TradingStyle.DAY_TRADING, preset=selected_preset,
                    candidates=candidates, universe_size=cycle.universe_size,
                    scanned=cycle.scanned, daily_target_usd=cycle.daily_target,
                    disclaimer="R-multiple sizing — scales with equity.",
                )
                st.session_state["tm_agent_advice"] = None
                if ADVISOR_OK and cycle.integrated_analyses:
                    try:
                        persona = st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT)
                        st.session_state["tm_agent_advice"] = explain_batch_summary(
                            cycle.integrated_analyses, persona,
                            st.session_state.get("tm_daily_target_pct", 0.75), equity,
                        )
                    except Exception:
                        pass
                st.session_state["tm_scan_result"] = result
                elapsed = round(_time.time() - t0, 1)
                progress.empty()
                st.success(
                    f"✅ Agent scan: {result.scanned} tickers in {elapsed}s — "
                    f"{len(result.candidates)} candidates (news + sentiment ranked)"
                )
                st.success(f"✅ Agent cycle: {cycle.message}")

                if cycle.exits:
                    st.info(f"Exits: {len(cycle.exits)} — " + ", ".join(
                        f"{e['ticker']} ({e['reason']}) ${e.get('pnl', 0):+.0f}" for e in cycle.exits[:5]
                    ))
                if cycle.entries:
                    st.success("Entries: " + ", ".join(
                        f"{e['ticker']} x{int(e['qty'])}" for e in cycle.entries
                    ))
                if cycle.blocked:
                    st.warning(f"Blocked: {len(cycle.blocked)} orders")

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Session P&L", f"${cycle.session_pnl:+,.2f}")
                with col_b:
                    st.metric("Daily target", f"${cycle.daily_target:,.0f}")
                with col_c:
                    st.metric("Target progress", f"{cycle.target_progress_pct:.0f}%")
            else:
                result = engine.scan(
                    style=style, preset=selected_preset, top_n=top_n,
                    daily_target_usd=st.session_state["tm_daily_target"],
                    account_equity=equity, progress_callback=_cb,
                    advisor_persona=st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT).value
                    if ADVISOR_OK else "warren_buffett",
                    enable_sentiment=True,
                )
                st.session_state["tm_agent_advice"] = None
                if ADVISOR_OK and result.integrated_analyses:
                    try:
                        persona = st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT)
                        tgt_pct = st.session_state.get("tm_daily_target_pct", 0.75)
                        st.session_state["tm_agent_advice"] = explain_batch_summary(
                            result.integrated_analyses, persona, tgt_pct, equity,
                        )
                    except Exception:
                        pass
                st.session_state["tm_scan_result"] = result
                elapsed = round(_time.time() - t0, 1)
                progress.empty()
                st.success(
                    f"✅ Scanned {result.universe_size} stocks in {elapsed}s — "
                    f"{len(result.candidates)} candidates"
                )
                if exec_pref == ExecutionPreference.AUTO:
                    auto_result = engine.auto_execute(
                        result, max_trades=int(auto_max), min_score=float(auto_min_score),
                        kill_switch=st.session_state.get("kill_switch", False),
                    )
                    if auto_result.executed:
                        st.success(f"🤖 Auto: {len(auto_result.executed)} order(s) placed")
                    if auto_result.message and not auto_result.executed:
                        st.info(auto_result.message)
        except Exception as e:
            progress.empty()
            st.error(f"Failed: {e}")

# ── Results ────────────────────────────────────────────────────────────────────
scan_result = st.session_state.get("tm_scan_result")

if scan_result and scan_result.candidates:
    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
    style_label = TRADING_STYLE_LABELS.get(scan_result.style, str(scan_result.style))
    st.markdown(f"<div class='sh'>5 · Results — {style_label}</div>", unsafe_allow_html=True)

    buys = sum(1 for c in scan_result.candidates if c.signal == "BUY_CANDIDATE")
    avg_score = sum(c.score for c in scan_result.candidates) / len(scan_result.candidates)
    top = scan_result.candidates[0]

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"<div class='mc'><div class='ml'>Universe</div><div class='mv'>{scan_result.universe_size}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='mc'><div class='ml'>Candidates</div><div class='mv' style='color:#00C853'>{len(scan_result.candidates)}</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='mc'><div class='ml'>Buy Signals</div><div class='mv' style='color:#00C853'>{buys}</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='mc'><div class='ml'>Avg Score</div><div class='mv'>{avg_score:.0f}</div></div>", unsafe_allow_html=True)
    with m5:
        st.markdown(f"<div class='mc'><div class='ml'>#1 Pick</div><div class='mv' style='color:#D4AF37'>{top.ticker}</div></div>", unsafe_allow_html=True)

    # Top pick spotlight
    st.markdown(f"**🏆 #{top.rank} {top.ticker}** — ${top.price:,.2f} · Score {top.score:.0f} · {top.signal}")
    if style == TradingStyle.MONTHLY_INCOME and top.est_daily_usd:
        st.caption(
            f"Conservative est. ~${top.est_daily_usd:,.0f}/day at suggested size "
            f"(target ref: ${scan_result.daily_target_usd:,.0f}/day) — NOT guaranteed"
        )
    elif style == TradingStyle.DAY_TRADING and top.raw and hasattr(top.raw, "sizing"):
        sz = top.raw.sizing
        st.caption(
            f"R-multiple setup: risk ${sz.risk_usd:,.0f} → reward ${sz.reward_usd:,.0f} "
            f"({sz.risk_reward_ratio:.0f}:1) · {sz.shares} shares · NOT guaranteed"
        )
    st.caption(top.explanation[:350])

    # Table
    rows = []
    for c in scan_result.candidates:
        row = {
            "Rank": c.rank,
            "Ticker": c.ticker,
            "Price": f"${c.price:,.2f}",
            "Signal": c.signal,
            "Score": f"{c.score:.1f}",
            "Shares": f"{c.quantity:.0f}",
            "Stop": f"${c.stop_loss:,.2f}",
            "Target": f"${c.take_profit:,.2f}",
        }
        if style == TradingStyle.DAY_TRADING:
            row["Tech"] = f"{getattr(c.raw, 'technical_score', c.score):.0f}" if c.raw else f"{c.score:.0f}"
            row["Sentiment"] = f"{getattr(c.raw, 'sentiment_score', 50):.0f}" if c.raw else "—"
            row["News"] = f"{getattr(c.raw, 'sentiment_label', '—')}" if c.raw else "—"
            row["Composite"] = f"{c.score:.1f}"
            if c.raw and hasattr(c.raw, "sizing"):
                row["Risk $"] = f"${c.raw.sizing.risk_usd:,.0f}"
                row["Reward $"] = f"${c.raw.sizing.reward_usd:,.0f}"
                row["R:R"] = f"{c.raw.sizing.risk_reward_ratio:.1f}:1"
            else:
                row["Est reward $"] = f"${c.est_daily_usd:,.0f}"
        elif style == TradingStyle.MONTHLY_INCOME:
            row["Est $/day"] = f"${c.est_daily_usd:,.0f}"
            ia = getattr(c.raw, "integrated", None) if c.raw else None
            if ia:
                row["Tech"] = f"{ia.technical_score:.0f}"
                row["Sentiment"] = f"{ia.sentiment_score:.0f}"
                row["News"] = ia.sentiment_label
                row["Composite"] = f"{ia.composite_score:.1f}"
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=min(600, 80 + len(df) * 36))

    # Chart top 15
    with st.expander("📊 Score chart (top 15)"):
        top15 = scan_result.candidates[:15]
        fig = go.Figure(go.Bar(
            x=[c.ticker for c in top15],
            y=[c.score for c in top15],
            marker_color=["#00C853" if c.signal == "BUY_CANDIDATE" else "#D4AF37" for c in top15],
        ))
        fig.update_layout(
            template="plotly_dark", height=320,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(18,18,38,0.5)",
            yaxis_title="Score", margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Institutional AI advisor panel
    agent_advice = st.session_state.get("tm_agent_advice")
    cycle = st.session_state.get("tm_agent_cycle")
    if ADVISOR_OK and (
        agent_advice
        or (cycle and cycle.integrated_analyses)
        or (scan_result and scan_result.integrated_analyses)
    ):
        st.markdown("<div class='sh'>🧠 Institutional AI Advisor — News + Sentiment Brief</div>", unsafe_allow_html=True)
        if agent_advice:
            st.markdown(agent_advice.full_text)
        elif top.raw and getattr(top.raw, "integrated", None):
            try:
                advice = explain_integrated(
                    top.raw.integrated,
                    st.session_state.get("tm_advisor_persona", AdvisorPersona.BUFFETT),
                    st.session_state.get("tm_daily_target_pct", 0.75),
                    st.session_state["tm_account_equity"],
                )
                st.markdown(advice.full_text)
            except Exception as ex:
                st.caption(f"Advisor: {ex}")

        integrated_top = getattr(top.raw, "integrated", None) if top.raw else None
        if integrated_top and integrated_top.news_headlines:
            with st.expander(f"📰 News headlines — {top.ticker}"):
                for n in integrated_top.news_headlines[:8]:
                    css = "news-bull" if n.sentiment_label == "BULLISH" else (
                        "news-bear" if n.sentiment_label == "BEARISH" else "news-neut"
                    )
                    st.markdown(
                        f"<div class='{css}'><strong>{n.sentiment_label}</strong> {n.title[:120]}"
                        f"<br><span style='font-size:0.75rem;color:#666;'>{n.source} · {n.published}</span></div>",
                        unsafe_allow_html=True,
                    )

        # Sr Wall Street deep research on top pick
        if ADVISOR_OK:
            try:
                from ai.wall_street_advisor import generate_research_note, generate_from_sentiment
                with st.expander(f"🏛️ Sr. Wall Street Deep Research — {top.ticker}", expanded=False):
                    if st.button(f"Generate full research note", key="tm_ws_note"):
                        with st.spinner("Sr. advisor analyzing..."):
                            integrated_top = getattr(top.raw, "integrated", None) if top.raw else None
                            if integrated_top:
                                ws = generate_research_note(
                                    integrated_top,
                                    st.session_state["tm_account_equity"],
                                    st.session_state.get("tm_daily_target_pct", 0.75),
                                )
                            elif top.raw and getattr(top.raw, "integrated", None):
                                ws = generate_research_note(
                                    top.raw.integrated,
                                    st.session_state["tm_account_equity"],
                                    st.session_state.get("tm_daily_target_pct", 0.75),
                                )
                            else:
                                ws = None
                            if ws:
                                st.session_state["tm_ws_note"] = ws
                    ws = st.session_state.get("tm_ws_note")
                    if ws and ws.ticker == top.ticker:
                        st.markdown(ws.full_report)
            except Exception:
                pass

    # Manual: propose trade
    if exec_pref == ExecutionPreference.MANUAL and QUEUE_OK:
        st.markdown("<div class='sh'>6 · Manual Trade — Pick & Propose</div>", unsafe_allow_html=True)
        st.caption("Approve in **Paper Trading**, or propose from **Strategy Signals**.")

        pick_labels = [
            f"#{c.rank} {c.ticker} — {c.signal} ({c.score:.0f})"
            for c in scan_result.candidates
        ]
        sel_i = st.selectbox("Select pick", range(len(pick_labels)), format_func=lambda i: pick_labels[i])
        pick = scan_result.candidates[sel_i]

        pc1, pc2 = st.columns([2, 3])
        with pc1:
            side = st.radio("Side", ["buy", "sell"], horizontal=True, key="tm_side")
            qty = st.number_input("Quantity", 1, max(1, int(pick.quantity * 2)),
                                  value=max(1, int(pick.quantity)), key="tm_qty")
            st.caption(f"Est. value: ${qty * pick.price:,.2f}")
        with pc2:
            rm = st.session_state.get("risk_manager")
            risk_dict = {"approved": True, "checks_passed": [], "checks_failed": []}
            if rm:
                from trading.risk_manager import RiskManager
                rr = rm.check_order(
                    symbol=pick.ticker, qty=float(qty), side=side, price=pick.price,
                    account_buying_power=st.session_state["tm_account_equity"],
                )
                risk_dict = {
                    "approved": rr.approved,
                    "checks_passed": rr.checks_passed,
                    "checks_failed": rr.checks_failed,
                }
                if rr.approved:
                    st.success(f"✅ Risk passed ({len(rr.checks_passed)} checks)")
                else:
                    st.error(f"❌ {rr.rejection_summary}")

        if st.button(f"📋 Propose {side.upper()} {qty}x {pick.ticker}", type="primary"):
            try:
                q = st.session_state["approval_queue"]
                bmode = "mock" if is_mock else ("live" if is_live else "paper")
                p = q.create_proposal(
                    ticker=pick.ticker, side=side, quantity=float(qty),
                    estimated_price=pick.price,
                    strategy_name=f"{style.value}:{selected_preset}",
                    signal_reason=pick.explanation[:300],
                    ai_explanation=f"Score {pick.score:.0f} | Mode: {style.value}",
                    risk_result=risk_dict, broker_mode=bmode,
                )
                st.success(f"✅ Proposal created — approve below (expires in 5 min)")
            except Exception as e:
                st.error(str(e))

    # Inline proposals (manual)
    if exec_pref == ExecutionPreference.MANUAL and QUEUE_OK:
        queue = st.session_state.get("approval_queue")
        if queue:
            queue.expire_stale_proposals()
            pending = queue.get_pending_proposals()
            approved = queue.get_approved_proposals()
            if pending or approved:
                st.markdown("<div class='sh'>📋 Pending Proposals</div>", unsafe_allow_html=True)
                for p in pending + approved:
                    cols = st.columns([4, 1, 1, 1])
                    with cols[0]:
                        st.write(f"**{p.status}** — {p.side.upper()} {p.quantity:.0f}x {p.ticker} @ ${p.estimated_price:.2f}")
                    if p.status == STATUS_PENDING:
                        with cols[1]:
                            if st.button("✅ Approve", key=f"a_{p.proposal_id[:8]}"):
                                queue.approve_proposal(p.proposal_id)
                                st.rerun()
                        with cols[2]:
                            if st.button("❌ Reject", key=f"r_{p.proposal_id[:8]}"):
                                queue.reject_proposal(p.proposal_id)
                                st.rerun()
                    elif p.status == STATUS_APPROVED:
                        with cols[1]:
                            if st.button("🚀 Execute", key=f"x_{p.proposal_id[:8]}", type="primary"):
                                try:
                                    queue.execute_proposal(p.proposal_id, broker=broker, current_price=p.estimated_price)
                                    st.success("Executed!")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(str(ex))

elif scan_result is None:
    st.markdown("""
    <div style='text-align:center;padding:3rem;color:#555;'>
      <div style='font-size:3rem;'>🚀</div>
      <p>Select a strategy and click <strong style='color:#D4AF37;'>SCAN US MARKET</strong></p>
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
broker_label = "MockBroker" if is_mock else ("Alpaca Paper" if not is_live else "LIVE")
st.caption(
    f"Broker: {broker_label} · "
    f"Auto paper: {'ON' if SETTINGS_OK and settings and settings.ENABLE_AUTO_MODE else 'OFF (set ENABLE_AUTO_MODE=true)'} · "
    f"Educational use only."
)

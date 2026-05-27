"""
Suggested Trades — Market Scanner + Day Trading Candidates + Approval-Based Execution

Features:
  - Scan 600+ stocks automatically, find the best day-trading setups
  - Or enter custom tickers
  - Ranked results with 8-dimension scores
  - One-click trade proposal → Approve → Execute via paper/live broker
  - Full safety: risk gate + approval required + kill switch respect

NOT FINANCIAL ADVICE. Day trading involves significant risk of loss.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time as _time

st.set_page_config(
    page_title="Suggested Trades | AI Trading Assistant",
    page_icon="🎯",
    layout="wide",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
:root{
  --gold:#D4AF37;--cyan:#00E5FF;--green:#00C853;--red:#FF1744;
  --amber:#FFA726;--purple:#CE93D8;--glass:rgba(18,18,38,0.85);
  --border:rgba(212,175,55,0.15);--bg:#06060F;
}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:var(--bg);}

/* Scanner hero */
.scanner-hero{
  background:linear-gradient(135deg,rgba(212,175,55,0.08) 0%,rgba(0,229,255,0.05) 50%,rgba(0,200,83,0.06) 100%);
  border:1px solid rgba(212,175,55,0.2);border-radius:16px;
  padding:1.6rem 2rem;margin-bottom:1.4rem;position:relative;overflow:hidden;
}
.scanner-hero::before{
  content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,#D4AF37,#00E5FF,#00C853);
}
.hero-title{font-size:2.2rem;font-weight:900;
  background:linear-gradient(135deg,#D4AF37,#F5E6A3,#00E5FF);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin:0 0 0.3rem;line-height:1.1;}
.hero-sub{color:#666;font-size:0.88rem;margin:0;}

/* Disclaimer */
.disc{background:linear-gradient(135deg,rgba(255,23,68,0.06),rgba(255,167,38,0.06));
  border:1px solid rgba(255,167,38,0.3);border-left:4px solid #FFA726;
  border-radius:10px;padding:0.75rem 1.1rem;margin-bottom:1.2rem;
  color:#FFA726;font-size:0.82rem;font-weight:600;line-height:1.5;}

/* Section header */
.sh{font-size:0.9rem;font-weight:800;color:var(--gold);text-transform:uppercase;
  letter-spacing:2px;padding-bottom:0.45rem;margin-bottom:0.9rem;
  border-bottom:1px solid rgba(212,175,55,0.18);}

/* Metric cards */
.mc{background:rgba(212,175,55,0.05);border:1px solid rgba(212,175,55,0.12);
  border-radius:10px;padding:0.75rem 1rem;text-align:center;}
.ml{font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:1.3px;color:#555;margin-bottom:0.2rem;}
.mv{font-size:1.35rem;font-weight:900;color:#fff;font-family:'JetBrains Mono',monospace;}

/* Card */
.card{background:var(--glass);backdrop-filter:blur(18px);border:1px solid var(--border);
  border-radius:14px;padding:1.2rem 1.4rem;margin-bottom:0.9rem;
  position:relative;overflow:hidden;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--gold),transparent);}

/* Scan preset pills */
.preset-active{background:rgba(212,175,55,0.18);border:1px solid #D4AF37;
  color:#D4AF37;border-radius:20px;padding:0.3rem 1rem;font-size:0.8rem;font-weight:700;}
.preset-inactive{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
  color:#666;border-radius:20px;padding:0.3rem 1rem;font-size:0.8rem;}

/* Signal badges */
.sig-buy{display:inline-block;padding:0.15rem 0.7rem;border-radius:20px;
  font-size:0.68rem;font-weight:800;letter-spacing:0.8px;
  background:rgba(0,200,83,0.15);color:#00C853;border:1px solid #00C853;}
.sig-watch{display:inline-block;padding:0.15rem 0.7rem;border-radius:20px;
  font-size:0.68rem;font-weight:800;
  background:rgba(212,175,55,0.15);color:#D4AF37;border:1px solid #D4AF37;}
.sig-avoid{display:inline-block;padding:0.15rem 0.7rem;border-radius:20px;
  font-size:0.68rem;font-weight:800;
  background:rgba(136,136,136,0.12);color:#888;border:1px solid #555;}

/* Tabs */
.gd{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);margin:1.2rem 0;border:none;}
.stTabs [data-baseweb="tab-list"]{gap:5px;}
.stTabs [data-baseweb="tab"]{background:rgba(18,18,38,0.6);border:1px solid rgba(212,175,55,0.08);
  border-radius:8px 8px 0 0;padding:8px 16px;color:#888;font-weight:600;font-size:0.88rem;}
.stTabs [aria-selected="true"]{background:rgba(212,175,55,0.1)!important;
  border-bottom:2px solid #D4AF37!important;color:#D4AF37!important;}

/* Live ticker bars */
.ticker-bar{font-family:'JetBrains Mono',monospace;font-size:0.8rem;padding:0.2rem 0.6rem;
  border-radius:6px;display:inline-block;margin:0.1rem;}
.ticker-up{background:rgba(0,200,83,0.1);color:#00C853;}
.ticker-down{background:rgba(255,23,68,0.1);color:#FF1744;}
.ticker-flat{background:rgba(212,175,55,0.08);color:#D4AF37;}

/* Score bar */
.score-bar-bg{background:rgba(255,255,255,0.06);border-radius:6px;height:8px;overflow:hidden;margin-top:0.25rem;}
.score-bar-fill{height:100%;border-radius:6px;transition:width 0.4s ease;}
</style>
""", unsafe_allow_html=True)

# ── Imports ────────────────────────────────────────────────────────────────────
SETTINGS_OK = False
settings = None
try:
    from db.database import init_db
    from config.settings import get_settings
    init_db()
    settings = get_settings()
    SETTINGS_OK = True
except Exception as e:
    st.error(f"Settings: {e}")

SCANNER_OK = False
try:
    from analysis.market_scanner import MarketScanner, SCAN_PRESETS, ScanSession, ScanResult
    from analysis.universe import get_universe, SECTORS
    SCANNER_OK = True
except Exception as e:
    st.error(f"Market scanner: {e}")

RANKER_OK = False
try:
    from analysis.stock_ranker import StockRanker
    RANKER_OK = True
except Exception:
    pass

QUEUE_OK = False
try:
    from trading.approval_queue import (
        ApprovalQueue, STATUS_PENDING, STATUS_APPROVED,
        STATUS_REJECTED, STATUS_EXPIRED, STATUS_EXECUTED,
    )
    QUEUE_OK = True
except Exception as e:
    st.error(f"Approval queue: {e}")

SIZER_OK = False
try:
    from trading.position_sizer import PositionSizer
    SIZER_OK = True
except Exception:
    pass

RISK_OK = False
try:
    from trading.risk_manager import RiskManager
    RISK_OK = True
except Exception:
    pass

# ── Session state ──────────────────────────────────────────────────────────────
defaults = {
    "scan_session": None,
    "scan_preset": "day_trading",
    "approval_queue": None,
    "broker": None,
    "risk_manager": None,
    "scanner_running": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state["approval_queue"] is None and QUEUE_OK:
    try:
        st.session_state["approval_queue"] = ApprovalQueue()
    except Exception:
        pass

if st.session_state["broker"] is None:
    try:
        from trading.mock_broker import MockBroker
        st.session_state["broker"] = MockBroker()
    except Exception:
        pass

if st.session_state["risk_manager"] is None and RISK_OK:
    try:
        st.session_state["risk_manager"] = RiskManager()
    except Exception:
        pass

# ── Helpers ────────────────────────────────────────────────────────────────────
broker = st.session_state.get("broker")
broker_can_trade = not (broker and hasattr(broker, 'CAN_TRADE') and not broker.CAN_TRADE)
is_live = SETTINGS_OK and settings and settings.ENABLE_LIVE_TRADING

# ── Hero Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class='scanner-hero'>
  <div class='hero-title'>🎯 Market Scanner — Find Top Day Trades</div>
  <div class='hero-sub'>
    Automatically scans 600+ stocks in real-time · Ranks by volume, momentum, RSI, MACD, gap &amp; trend ·
    Paper trade any candidate instantly · Not financial advice
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='disc'>
  ⚠️ <strong>NOT FINANCIAL ADVICE.</strong>
  <strong>Tip:</strong> For full US stock list with strategy + sentiment ranking, use
  <strong>📊 Strategy Signals</strong> in the sidebar (Robinhood 500+ stocks, same propose-trade flow).
</div>
""", unsafe_allow_html=True)

if is_live:
    st.error("🚨 **LIVE TRADING ACTIVE** — Real orders will use real money. Be extremely careful.")
if not broker_can_trade:
    st.warning("🔍 **Robinhood Watchlist Mode** — Analysis only. Switch broker in Settings to trade.")

# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_scan, tab_custom, tab_proposals = st.tabs([
    "🔥 Market Scanner",
    "🔎 Custom Tickers",
    "📋 Proposals & Execution",
])


# ──────────────────────────────────────────────────────────────────────────────
#  TAB 1 — MARKET SCANNER
# ──────────────────────────────────────────────────────────────────────────────
with tab_scan:
    st.markdown("<div class='sh'>⚡ Scan the Market — Auto-Find Best Day Trading Candidates</div>", unsafe_allow_html=True)

    # Preset selector
    col_presets = st.columns(len(SCAN_PRESETS))
    preset_keys = list(SCAN_PRESETS.keys())
    preset_vals = list(SCAN_PRESETS.values())

    current_preset = st.session_state.get("scan_preset", "day_trading")
    selected_preset_label = next(
        (k for k, v in SCAN_PRESETS.items() if v == current_preset),
        preset_keys[0]
    )

    for i, (label, val) in enumerate(SCAN_PRESETS.items()):
        with col_presets[i]:
            if st.button(label, key=f"preset_{i}", use_container_width=True,
                         type="primary" if val == current_preset else "secondary"):
                st.session_state["scan_preset"] = val
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Scanner controls
    sc1, sc2, sc3, sc4 = st.columns([2, 1, 1, 1])
    with sc1:
        top_n = st.slider("Top N results to show", min_value=10, max_value=50, value=25, step=5, key="top_n_slider")
    with sc2:
        min_price = st.number_input("Min price ($)", min_value=0.5, max_value=50.0, value=3.0, step=0.5, key="min_px")
    with sc3:
        min_vol_m = st.number_input("Min avg volume (M)", min_value=0.1, max_value=5.0, value=0.5, step=0.1, key="min_vol")
    with sc4:
        stop_pct = st.number_input("Stop-loss %", min_value=0.5, max_value=5.0, value=2.0, step=0.5, key="sl_pct")

    universe = get_universe(current_preset) if SCANNER_OK else []
    st.caption(f"📊 Universe: **{len(universe)} stocks** in **{selected_preset_label}** | Scan fetches live data from Yahoo Finance")

    scan_col, info_col = st.columns([1, 3])
    with scan_col:
        scan_btn = st.button("🚀 SCAN NOW", type="primary", use_container_width=True, key="scan_btn",
                             disabled=not SCANNER_OK)
    with info_col:
        if not SCANNER_OK:
            st.error("Market scanner module not available.")
        else:
            st.info(f"💡 Scans {len(universe)} tickers in parallel. Takes 20-60 seconds depending on universe size.")

    # ── Run scan ───────────────────────────────────────────────────────────────
    if scan_btn and SCANNER_OK:
        progress_bar = st.progress(0, text="Initializing scanner...")
        status_text = st.empty()
        completed_ref = [0]
        total_ref = [len(universe)]

        def progress_cb(done, total):
            completed_ref[0] = done
            pct = done / total
            progress_bar.progress(pct, text=f"Scanning... {done}/{total} tickers analyzed")

        with st.spinner(""):
            try:
                t0 = _time.time()
                scanner = MarketScanner(
                    max_workers=20,
                    min_price=min_price,
                    min_avg_volume=int(min_vol_m * 1_000_000),
                    top_n=top_n,
                    stop_loss_pct=stop_pct,
                    take_profit_pct=stop_pct * 2.0,
                )
                session = scanner.scan(preset=current_preset, progress_callback=progress_cb)
                st.session_state["scan_session"] = session
                elapsed = round(_time.time() - t0, 1)
                progress_bar.progress(1.0, text=f"✅ Complete! Scanned {session.scanned} stocks in {elapsed}s")
                _time.sleep(0.5)
                progress_bar.empty()
                st.success(
                    f"✅ **Scan complete!** Found top {len(session.results)} candidates "
                    f"from {session.universe_size} stocks in {elapsed}s"
                )
            except Exception as e:
                progress_bar.empty()
                st.error(f"Scan failed: {e}")

    # ── Results ───────────────────────────────────────────────────────────────
    session: ScanSession = st.session_state.get("scan_session")

    if session and session.results:
        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

        # ── Summary metrics ────────────────────────────────────────────────────
        buy_ct   = sum(1 for r in session.results if r.signal == "BUY_CANDIDATE")
        watch_ct = sum(1 for r in session.results if r.signal == "WATCH")
        avg_vol  = sum(r.volume_ratio for r in session.results) / len(session.results)
        avg_score = sum(r.overall_score for r in session.results) / len(session.results)
        top1 = session.top

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: st.markdown(f"<div class='mc'><div class='ml'>Universe Scanned</div><div class='mv'>{session.universe_size}</div></div>", unsafe_allow_html=True)
        with m2: st.markdown(f"<div class='mc'><div class='ml'>Top Candidates</div><div class='mv' style='color:#00C853;'>{len(session.results)}</div></div>", unsafe_allow_html=True)
        with m3: st.markdown(f"<div class='mc'><div class='ml'>Buy Signals</div><div class='mv' style='color:#00C853;'>{buy_ct}</div></div>", unsafe_allow_html=True)
        with m4: st.markdown(f"<div class='mc'><div class='ml'>Avg Vol Ratio</div><div class='mv' style='color:#FFA726;'>{avg_vol:.1f}x</div></div>", unsafe_allow_html=True)
        with m5: st.markdown(f"<div class='mc'><div class='ml'>Scan Time</div><div class='mv' style='color:#00E5FF;'>{session.elapsed_seconds:.0f}s</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── #1 Top Pick spotlight ──────────────────────────────────────────────
        if top1:
            st.markdown("<div class='sh'>🏆 #1 Top Day Trade Candidate (Not Financial Advice)</div>", unsafe_allow_html=True)
            sp1, sp2, sp3 = st.columns([2, 2, 2])
            with sp1:
                chg_color = "#00C853" if top1.change_pct_1d >= 0 else "#FF1744"
                st.markdown(f"""
                <div class='card'>
                  <div style='font-size:2rem;font-weight:900;color:#D4AF37;'>{top1.ticker}</div>
                  <div style='font-size:1.3rem;font-weight:800;color:#fff;font-family:JetBrains Mono,monospace;'>${top1.price:,.2f}</div>
                  <div style='font-size:1rem;font-weight:700;color:{chg_color};'>{top1.change_pct_1d:+.2f}% today &nbsp;|&nbsp; {top1.change_pct_5d:+.2f}% 5-day</div>
                  <div style='margin-top:0.6rem;font-size:0.75rem;color:#888;'>{top1.explanation[:200]}</div>
                </div>
                """, unsafe_allow_html=True)
            with sp2:
                st.markdown(f"""
                <div class='card'>
                  <div style='font-size:0.62rem;color:#555;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:0.6rem;'>Day Trading Scores</div>
                  <div style='margin-bottom:0.5rem;'>
                    <div style='display:flex;justify-content:space-between;font-size:0.78rem;'><span style='color:#888;'>Volume Surge</span><span style='color:#FFA726;font-weight:700;'>{top1.volume_score:.0f}/100 ({top1.volume_ratio:.1f}x avg)</span></div>
                    <div class='score-bar-bg'><div class='score-bar-fill' style='width:{top1.volume_score}%;background:#FFA726;'></div></div>
                  </div>
                  <div style='margin-bottom:0.5rem;'>
                    <div style='display:flex;justify-content:space-between;font-size:0.78rem;'><span style='color:#888;'>Momentum</span><span style='color:#CE93D8;font-weight:700;'>{top1.momentum_score:.0f}/100</span></div>
                    <div class='score-bar-bg'><div class='score-bar-fill' style='width:{top1.momentum_score}%;background:#CE93D8;'></div></div>
                  </div>
                  <div style='margin-bottom:0.5rem;'>
                    <div style='display:flex;justify-content:space-between;font-size:0.78rem;'><span style='color:#888;'>RSI Zone</span><span style='color:#00E5FF;font-weight:700;'>{top1.rsi_score:.0f}/100 (RSI {top1.rsi:.0f})</span></div>
                    <div class='score-bar-bg'><div class='score-bar-fill' style='width:{top1.rsi_score}%;background:#00E5FF;'></div></div>
                  </div>
                  <div>
                    <div style='display:flex;justify-content:space-between;font-size:0.78rem;'><span style='color:#888;'>Overall Score</span><span style='color:#D4AF37;font-weight:800;'>{top1.overall_score:.1f}/100</span></div>
                    <div class='score-bar-bg'><div class='score-bar-fill' style='width:{top1.overall_score}%;background:linear-gradient(90deg,#D4AF37,#00E5FF);'></div></div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with sp3:
                st.markdown(f"""
                <div class='card'>
                  <div style='font-size:0.62rem;color:#555;text-transform:uppercase;letter-spacing:1.2px;margin-bottom:0.6rem;'>Rule-Engine Levels (Not Advice)</div>
                  <div style='display:flex;justify-content:space-between;margin-bottom:0.45rem;'><span style='color:#888;font-size:0.8rem;'>Current Price</span><span style='color:#fff;font-weight:800;font-family:JetBrains Mono,monospace;'>${top1.price:,.2f}</span></div>
                  <div style='display:flex;justify-content:space-between;margin-bottom:0.45rem;'><span style='color:#888;font-size:0.8rem;'>Stop Loss (-{stop_pct:.0f}%)</span><span style='color:#FF1744;font-weight:800;font-family:JetBrains Mono,monospace;'>${top1.stop_loss_price:,.2f}</span></div>
                  <div style='display:flex;justify-content:space-between;margin-bottom:0.45rem;'><span style='color:#888;font-size:0.8rem;'>Take Profit (+{stop_pct*2:.0f}%)</span><span style='color:#00C853;font-weight:800;font-family:JetBrains Mono,monospace;'>${top1.take_profit_price:,.2f}</span></div>
                  <div style='display:flex;justify-content:space-between;margin-bottom:0.45rem;'><span style='color:#888;font-size:0.8rem;'>Volume Ratio</span><span style='color:#FFA726;font-weight:700;font-family:JetBrains Mono,monospace;'>{top1.volume_ratio:.2f}x</span></div>
                  <div style='display:flex;justify-content:space-between;margin-bottom:0.45rem;'><span style='color:#888;font-size:0.8rem;'>ATR (Daily Range)</span><span style='color:#CE93D8;font-family:JetBrains Mono,monospace;'>{top1.atr_pct:.2f}%</span></div>
                  <div style='display:flex;justify-content:space-between;'><span style='color:#888;font-size:0.8rem;'>Gap at Open</span><span style='color:#D4AF37;font-family:JetBrains Mono,monospace;'>{top1.gap_pct:+.2f}%</span></div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

        # ── Full ranked table ──────────────────────────────────────────────────
        st.markdown(f"<div class='sh'>📊 Top {len(session.results)} Day Trading Candidates — Ranked Best → Worst</div>", unsafe_allow_html=True)
        st.caption("⚠️ Rankings are based on technical indicators only. Not financial advice. Paper trade before going live.")

        df = session.as_dataframe

        def _clr_sig(v):
            return {
                "BUY_CANDIDATE": "color:#00C853;font-weight:800;",
                "WATCH": "color:#D4AF37;font-weight:700;",
                "AVOID": "color:#888;",
            }.get(str(v), "")

        def _clr_1d(v):
            try:
                val = float(str(v).replace("%","").replace("+",""))
                return "color:#00C853;font-weight:700;" if val > 0 else ("color:#FF1744;font-weight:700;" if val < 0 else "")
            except Exception:
                return ""

        def _clr_vr(v):
            try:
                val = float(str(v).replace("x",""))
                if val >= 2.0: return "color:#FFA726;font-weight:800;"
                if val >= 1.5: return "color:#FFA726;font-weight:600;"
                return ""
            except Exception:
                return ""

        styled = (
            df.style
            .map(_clr_sig, subset=["Signal"])
            .map(_clr_1d, subset=["1D Change"])
            .map(_clr_vr, subset=["Volume Ratio"])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

        # ── Score breakdown chart ──────────────────────────────────────────────
        with st.expander("📊 Score Breakdown Chart (Top 15)", expanded=False):
            top15 = session.results[:15]
            fig = go.Figure()
            colors_map = {
                "Volume": "#FFA726", "Momentum": "#CE93D8",
                "RSI": "#00E5FF", "MACD": "#00C853", "Trend": "#D4AF37",
            }
            score_attrs = [
                ("Volume",   [r.volume_score for r in top15]),
                ("Momentum", [r.momentum_score for r in top15]),
                ("RSI",      [r.rsi_score for r in top15]),
                ("MACD",     [r.macd_score for r in top15]),
                ("Trend",    [r.trend_score for r in top15]),
            ]
            for name, vals in score_attrs:
                fig.add_trace(go.Bar(
                    name=name, x=[r.ticker for r in top15], y=vals,
                    marker_color=colors_map[name], opacity=0.85,
                ))
            fig.update_layout(
                barmode="group", template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(18,18,38,0.5)",
                height=380, margin=dict(l=0,r=0,t=20,b=0),
                legend=dict(orientation="h", y=-0.15),
                yaxis=dict(title="Score", gridcolor="rgba(255,255,255,0.05)"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.03)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

        # ── Propose Trade section ──────────────────────────────────────────────
        st.markdown("<div class='sh'>💼 Create Trade Proposal from Scan Results</div>", unsafe_allow_html=True)

        if not broker_can_trade:
            st.warning("🔍 Switch broker in ⚙️ Settings to enable trading.")
        elif not QUEUE_OK:
            st.error("Approval queue not available.")
        else:
            valid_results = [r for r in session.results if r.is_valid]
            ticker_options = [f"#{r.rank} {r.ticker} — Score {r.overall_score:.0f} | {r.signal}" for r in valid_results]

            sel_idx = st.selectbox("Select ticker to propose", range(len(ticker_options)),
                                   format_func=lambda i: ticker_options[i], key="scan_propose_idx")
            sel_result: ScanResult = valid_results[sel_idx]

            pr1, pr2 = st.columns([2, 3])
            with pr1:
                prop_side = st.radio("Side", ["buy", "sell"], horizontal=True, key="scan_side")
                est_price = sel_result.price

                account_equity = 10000.0
                if broker and hasattr(broker, 'get_account'):
                    try:
                        acct = broker.get_account()
                        account_equity = float(acct.get("equity", 10000.0) or 10000.0)
                    except Exception:
                        pass

                max_qty, sz_warn = 10.0, ""
                if SIZER_OK and est_price > 0:
                    try:
                        sizing = PositionSizer().calculate(
                            current_price=est_price,
                            account_equity=account_equity,
                            stop_loss_price=sel_result.stop_loss_price,
                            atr_pct=sel_result.atr_pct,
                        )
                        max_qty = max(1.0, sizing.max_allowed_qty)
                        sz_warn = sizing.warning
                    except Exception:
                        pass

                prop_qty = st.number_input(f"Qty (max {int(max_qty)})", min_value=1,
                                           max_value=max(1, int(max_qty)),
                                           value=max(1, min(5, int(max_qty))), key="scan_qty")
                if sz_warn:
                    st.caption(f"⚠️ {sz_warn}")
                order_val = prop_qty * est_price
                st.markdown(f"<div style='font-size:0.82rem;color:#888;margin-top:0.4rem;'>Est: <strong style='color:#D4AF37;font-family:JetBrains Mono,monospace;'>${est_price:,.2f}</strong> × {prop_qty} = <strong style='color:#00E5FF;font-family:JetBrains Mono,monospace;'>${order_val:,.2f}</strong></div>", unsafe_allow_html=True)

            with pr2:
                st.markdown("**Pre-Trade Risk Check**")
                rm = st.session_state.get("risk_manager")
                risk_dict = {"approved": True, "checks_passed": [], "checks_failed": [], "details": {}}
                if rm and est_price > 0:
                    try:
                        rr = rm.approve_trade(symbol=sel_result.ticker, qty=float(prop_qty),
                                              side=prop_side, price=est_price)
                        risk_dict = {"approved": rr.approved, "checks_passed": rr.checks_passed,
                                     "checks_failed": rr.checks_failed, "details": rr.details}
                        if rr.approved:
                            st.success(f"✅ Risk passed ({len(rr.checks_passed)}/12)")
                        else:
                            st.error(f"❌ Blocked: {rr.rejection_summary}")
                    except Exception as e:
                        st.warning(f"Risk check error: {e}")
                else:
                    st.info("Risk manager unavailable — proposal created for manual review.")

            if st.button(f"📋 Propose: {prop_side.upper()} {prop_qty}x {sel_result.ticker}",
                         type="primary", key="scan_propose_btn"):
                try:
                    q = st.session_state["approval_queue"]
                    bmode = "mock" if (broker and hasattr(broker,'_initial_capital')) else \
                            ("live" if is_live else "paper")
                    proposal = q.create_proposal(
                        ticker=sel_result.ticker, side=prop_side, quantity=float(prop_qty),
                        estimated_price=est_price, strategy_name=f"MarketScanner:{current_preset}",
                        signal_reason=sel_result.explanation[:300],
                        ai_explanation=f"Score {sel_result.overall_score:.0f}/100 | Vol {sel_result.volume_ratio:.1f}x | RSI {sel_result.rsi:.0f}",
                        risk_result=risk_dict, broker_mode=bmode,
                    )
                    expiry = settings.APPROVAL_EXPIRY_MINUTES if SETTINGS_OK and settings else 5
                    st.success(f"✅ Proposal created! ID: `{proposal.proposal_id[:12]}...` Expires in {expiry} min")
                    st.info("👉 Switch to **📋 Proposals & Execution** tab to approve and execute.")
                except Exception as e:
                    st.error(f"Failed: {e}")

    elif not session:
        st.markdown("""
        <div style='text-align:center;padding:3rem 1rem;color:#555;'>
          <div style='font-size:3rem;margin-bottom:1rem;'>🔍</div>
          <div style='font-size:1.1rem;font-weight:700;color:#888;margin-bottom:0.5rem;'>Ready to Scan</div>
          <div style='font-size:0.85rem;'>Select a preset above and click <strong style='color:#D4AF37;'>SCAN NOW</strong> to find today's best day trading setups.</div>
        </div>
        """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
#  TAB 2 — CUSTOM TICKERS
# ──────────────────────────────────────────────────────────────────────────────
with tab_custom:
    st.markdown("<div class='sh'>🔎 Analyze Custom Tickers</div>", unsafe_allow_html=True)
    st.caption("Enter any US stock tickers — app will fetch live data and rank them.")

    DEFAULT_TICKERS = "AAPL, MSFT, NVDA, TSLA, AMD, META, GOOGL, AMZN, COIN, MSTR, RIOT, MARA"

    ci1, ci2 = st.columns([5, 1])
    with ci1:
        custom_input = st.text_input("Enter tickers (comma-separated)", value=DEFAULT_TICKERS,
                                     key="custom_tickers", label_visibility="collapsed")
    with ci2:
        custom_btn = st.button("🔍 Analyze", type="primary", use_container_width=True, key="custom_analyze_btn")

    with st.expander("⚙️ Analysis Settings"):
        ca1, ca2 = st.columns(2)
        with ca1:
            c_portfolio_val = st.number_input("Portfolio value (USD)", value=10000.0, step=1000.0, key="c_pv")
        with ca2:
            c_max_alloc = st.number_input("Max % per ticker", value=20.0, step=1.0, key="c_ma")

    if custom_btn:
        if not RANKER_OK:
            st.error("Stock ranker not available.")
        else:
            tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
            if not tickers:
                st.warning("Enter at least one ticker.")
            elif len(tickers) > 25:
                st.warning("Maximum 25 custom tickers at once.")
            else:
                with st.spinner(f"⚡ Analyzing {len(tickers)} tickers..."):
                    try:
                        ranker = StockRanker(
                            max_workers=10,
                            stop_loss_pct=settings.STOP_LOSS_PCT if SETTINGS_OK and settings else 2.0,
                            take_profit_pct=settings.TAKE_PROFIT_PCT if SETTINGS_OK and settings else 4.0,
                        )
                        result = ranker.rank(tickers, portfolio_value=c_portfolio_val, max_allocation_pct=c_max_alloc)
                        st.session_state["custom_ranking"] = result
                        st.success(f"✅ Analyzed {len(result.ranked)} tickers.")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

    custom_result = st.session_state.get("custom_ranking")
    if custom_result and custom_result.ranked:
        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
        df_c = pd.DataFrame(custom_result.as_dict_list)

        def _clr_s(v):
            return {"BUY_CANDIDATE":"color:#00C853;font-weight:800;","SELL_CANDIDATE":"color:#FF1744;",
                    "WATCH":"color:#D4AF37;","AVOID":"color:#888;"}.get(str(v),"")
        def _clr_a(v):
            return "color:#00C853;font-weight:700;" if "Consider" in str(v) else ("color:#FF1744;" if "Avoid" in str(v) else "color:#D4AF37;")

        cols = ["Rank","Ticker","Price","Signal","Confidence","Risk","Trend","Momentum","Overall Score","Action","Stop Loss","Take Profit"]
        avail = [c for c in cols if c in df_c.columns]
        st.dataframe(
            df_c[avail].style.map(_clr_s, subset=["Signal"] if "Signal" in avail else []).map(_clr_a, subset=["Action"] if "Action" in avail else []),
            use_container_width=True, hide_index=True, height=min(500, 80 + len(df_c)*38)
        )

        # Propose from custom
        if QUEUE_OK and broker_can_trade:
            st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
            st.markdown("<div class='sh'>💼 Propose Trade from Custom Analysis</div>", unsafe_allow_html=True)
            valid_custom = [r for r in custom_result.ranked if not r.analysis.error]
            if valid_custom:
                sel_c = st.selectbox("Select ticker", [r.ticker for r in valid_custom], key="custom_sel")
                sel_cr = next((r for r in valid_custom if r.ticker == sel_c), None)
                if sel_cr:
                    cc1, cc2 = st.columns([2,3])
                    with cc1:
                        c_side = st.radio("Side", ["buy","sell"], horizontal=True, key="c_side")
                        c_price = sel_cr.price
                        c_max_qty = 10.0
                        if SIZER_OK and c_price > 0:
                            try:
                                c_max_qty = max(1.0, PositionSizer().calculate(
                                    current_price=c_price, account_equity=10000.0,
                                    stop_loss_price=sel_cr.analysis.stop_loss_price,
                                ).max_allowed_qty)
                            except Exception:
                                pass
                        c_qty = st.number_input("Qty", min_value=1, max_value=max(1,int(c_max_qty)),
                                                value=max(1,min(5,int(c_max_qty))), key="c_qty")
                        st.caption(f"Est value: ${c_qty * c_price:,.2f}")
                    with cc2:
                        rm = st.session_state.get("risk_manager")
                        risk_d = {"approved":True,"checks_passed":[],"checks_failed":[],"details":{}}
                        if rm and c_price > 0:
                            try:
                                rr = rm.approve_trade(symbol=sel_c, qty=float(c_qty), side=c_side, price=c_price)
                                risk_d = {"approved":rr.approved,"checks_passed":rr.checks_passed,
                                          "checks_failed":rr.checks_failed,"details":rr.details}
                                if rr.approved: st.success(f"✅ Risk passed")
                                else: st.error(f"❌ Blocked: {rr.rejection_summary}")
                            except Exception as e:
                                st.warning(f"Risk: {e}")
                    if st.button(f"📋 Propose {c_side.upper()} {c_qty}x {sel_c}", type="primary", key="c_propose_btn"):
                        try:
                            bmode = "mock" if (broker and hasattr(broker,'_initial_capital')) else ("live" if is_live else "paper")
                            p = st.session_state["approval_queue"].create_proposal(
                                ticker=sel_c, side=c_side, quantity=float(c_qty),
                                estimated_price=c_price, strategy_name="CustomAnalysis",
                                signal_reason=sel_cr.explanation[:200],
                                ai_explanation=f"Score {sel_cr.overall_score:.0f}/100",
                                risk_result=risk_d, broker_mode=bmode,
                            )
                            st.success(f"✅ Proposal `{p.proposal_id[:12]}...` created. Go to Proposals tab.")
                        except Exception as e:
                            st.error(f"Failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
#  TAB 3 — PROPOSALS & EXECUTION
# ──────────────────────────────────────────────────────────────────────────────
with tab_proposals:
    st.markdown("<div class='sh'>📋 Trade Proposals — Review, Approve & Execute</div>", unsafe_allow_html=True)
    st.caption("⚠️ All proposals must be manually approved. AI cannot approve trades. Expired proposals cannot execute.")

    queue = st.session_state.get("approval_queue")
    if not QUEUE_OK or queue is None:
        st.error("Approval queue not available.")
    else:
        pc1, pc2 = st.columns([2,1])
        with pc1:
            if st.button("🔄 Refresh", key="refresh_props"): st.rerun()
        with pc2:
            show_all = st.checkbox("Show all statuses", value=False, key="show_all")

        queue.expire_stale_proposals()
        proposals = queue.get_all_proposals() if show_all else (
            queue.get_pending_proposals() + queue.get_approved_proposals()
        )

        if not proposals:
            st.markdown("""
            <div style='text-align:center;padding:3rem;color:#555;'>
              <div style='font-size:2.5rem;'>📭</div>
              <div style='margin-top:0.5rem;'>No proposals yet. Run a scan and click <strong>Propose</strong>.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            pn = sum(1 for p in proposals if p.status == STATUS_PENDING)
            pa = sum(1 for p in proposals if p.status == STATUS_APPROVED)
            pe = sum(1 for p in proposals if p.status == STATUS_EXECUTED)
            pr = sum(1 for p in proposals if p.status in (STATUS_REJECTED, STATUS_EXPIRED))

            ps1,ps2,ps3,ps4 = st.columns(4)
            with ps1: st.markdown(f"<div class='mc'><div class='ml'>Pending</div><div class='mv' style='color:#FFA726;'>{pn}</div></div>", unsafe_allow_html=True)
            with ps2: st.markdown(f"<div class='mc'><div class='ml'>Approved</div><div class='mv' style='color:#00E5FF;'>{pa}</div></div>", unsafe_allow_html=True)
            with ps3: st.markdown(f"<div class='mc'><div class='ml'>Executed</div><div class='mv' style='color:#00C853;'>{pe}</div></div>", unsafe_allow_html=True)
            with ps4: st.markdown(f"<div class='mc'><div class='ml'>Rejected/Expired</div><div class='mv' style='color:#FF1744;'>{pr}</div></div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            icons = {STATUS_PENDING:"⏳",STATUS_APPROVED:"✅",STATUS_EXECUTED:"✔️",
                     STATUS_REJECTED:"❌",STATUS_EXPIRED:"⌛"}

            for p in sorted(proposals, key=lambda x: x.created_at, reverse=True):
                icon = icons.get(p.status,"❓")
                secs = p.seconds_remaining
                tlabel = (f"Expires in {int(secs//60)}m {int(secs%60)}s"
                          if p.status in (STATUS_PENDING, STATUS_APPROVED) and secs > 0
                          else ("EXPIRED" if p.status in (STATUS_PENDING, STATUS_APPROVED) else ""))

                with st.expander(
                    f"{icon} [{p.status}] {p.side.upper()} {p.quantity:.0f}x {p.ticker} "
                    f"@ ${p.estimated_price:.2f}  •  {p.strategy_name}  {tlabel}",
                    expanded=(p.status == STATUS_PENDING)
                ):
                    d1, d2 = st.columns(2)
                    with d1:
                        st.markdown(f"""
**Ticker:** `{p.ticker}` | **Side:** `{p.side.upper()}` | **Qty:** `{p.quantity:.0f}`
**Est. Price:** `${p.estimated_price:,.2f}` | **Est. Value:** `${p.estimated_order_value:,.2f}`
**Mode:** `{p.broker_mode}` | **Strategy:** `{p.strategy_name}`
**Created:** `{str(p.created_at)[:19]}` | **Expires:** `{str(p.expires_at)[:19] if p.expires_at else 'N/A'}`
**ID:** `{p.proposal_id[:16]}...`""")
                    with d2:
                        r = p.risk_result or {}
                        if r.get("approved", True):
                            st.success("✅ Risk check passed at creation")
                        else:
                            st.error(f"❌ Risk blocked: {', '.join(r.get('checks_failed', []))}")

                    if p.signal_reason:
                        with st.expander("📊 Signal", expanded=False):
                            st.caption(p.signal_reason[:400])

                    # Action buttons
                    if p.status == STATUS_PENDING:
                        ba1, ba2, ba3 = st.columns([1,2,1])
                        with ba1:
                            if st.button("✅ Approve", key=f"ap_{p.proposal_id[:8]}", type="primary"):
                                try:
                                    queue.approve_proposal(p.proposal_id, approved_by="user")
                                    st.success("✅ Approved! Now click Execute.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")
                        with ba2:
                            rr_txt = st.text_input("", placeholder="Rejection reason (optional)",
                                                   key=f"rr_{p.proposal_id[:8]}", label_visibility="collapsed")
                        with ba3:
                            if st.button("❌ Reject", key=f"rj_{p.proposal_id[:8]}"):
                                try:
                                    queue.reject_proposal(p.proposal_id, reason=rr_txt, rejected_by="user")
                                    st.warning("Rejected.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")

                    elif p.status == STATUS_APPROVED:
                        ex1, ex2 = st.columns([1,3])
                        with ex1:
                            if st.button("🚀 Execute", key=f"ex_{p.proposal_id[:8]}", type="primary"):
                                if not broker_can_trade:
                                    st.error("Broker cannot trade.")
                                elif not broker:
                                    st.error("No broker connected.")
                                else:
                                    try:
                                        order = queue.execute_proposal(p.proposal_id, broker=broker,
                                                                       current_price=p.estimated_price)
                                        st.success(f"🎉 Executed! Order: {order.get('id','N/A')}")
                                        st.balloons()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Execution failed: {e}")
                        with ex2:
                            if tlabel: st.info(f"⏰ {tlabel}")

                    elif p.status == STATUS_EXECUTED:
                        fill = f"${p.fill_price:,.2f}" if p.fill_price else "N/A"
                        st.success(f"✔️ Executed | Fill: {fill}")
                    elif p.status == STATUS_REJECTED:
                        st.error("❌ Rejected.")
                    elif p.status == STATUS_EXPIRED:
                        st.warning("⌛ Expired — create a new proposal.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='font-size:0.7rem;color:#333;text-align:center;line-height:1.8;'>
  ⚠️ <strong>NOT FINANCIAL ADVICE.</strong> Day trading involves significant risk of loss.
  Technical indicators do not guarantee profit. Past patterns do not predict future results.<br>
  Paper trade first using Alpaca Paper Trading. Never risk money you cannot afford to lose.<br>
  Robinhood mode: watchlist/analysis only. Auto-trading disabled by default.
  All orders require explicit user approval.
</div>
""", unsafe_allow_html=True)

"""
US Market Sentiment — broad US equity sentiment sweep.

How real trading desks monitor the market:
  - Full US universe sentiment scan
  - Sector breadth & market-wide bullish/bearish %
  - Top sentiment leaders & momentum shifts
  - Sr. Wall Street deep research on any pick

NOT FINANCIAL ADVICE.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time as _time

from ui.auto_scan import (
    DEFAULT_SCAN_LIMIT,
    get_ui_poll_seconds,
    format_scan_status,
)
from ui.scan_service import resolve_us_scan

st.set_page_config(
    page_title="US Market | AI Trading Assistant",
    page_icon="📡",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--gold:#D4AF37;--cyan:#00E5FF;--green:#00C853;--red:#FF1744;--bg:#06060F;}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:var(--bg);}
.hero{background:linear-gradient(135deg,rgba(0,100,200,0.12),rgba(212,175,55,0.08));
  border:1px solid rgba(0,150,255,0.25);border-radius:16px;padding:1.5rem 2rem;margin-bottom:1rem;}
.hero h1{margin:0;font-size:2rem;font-weight:900;
  background:linear-gradient(135deg,#4FC3F7,#D4AF37);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.sh{font-size:0.88rem;font-weight:800;color:#D4AF37;text-transform:uppercase;
  letter-spacing:2px;border-bottom:1px solid rgba(212,175,55,0.15);padding-bottom:0.4rem;margin-bottom:0.8rem;}
.mc{background:rgba(212,175,55,0.05);border:1px solid rgba(212,175,55,0.12);
  border-radius:10px;padding:0.7rem;text-align:center;}
.ml{font-size:0.62rem;color:#666;text-transform:uppercase;letter-spacing:1px;}
.mv{font-size:1.4rem;font-weight:900;color:#fff;font-family:'JetBrains Mono',monospace;}
.disc{background:rgba(255,167,38,0.06);border-left:4px solid #FFA726;border-radius:8px;
  padding:0.75rem 1rem;margin:1rem 0;color:#FFA726;font-size:0.82rem;font-weight:600;}
.gd{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);margin:1.2rem 0;}
.news-bull{background:rgba(0,200,83,0.08);border-left:3px solid #00C853;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
.news-bear{background:rgba(255,23,68,0.08);border-left:3px solid #FF1744;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
.news-neut{background:rgba(150,150,150,0.06);border-left:3px solid #888;padding:0.5rem 0.75rem;margin:0.3rem 0;border-radius:6px;}
</style>
""", unsafe_allow_html=True)

SCANNER_OK = False
ADVISOR_OK = False
try:
    from analysis.us_market_sentiment import USMarketSentimentScanner, US_SENTIMENT_PRESETS
    from analysis.universe import get_price_bounds
    SCANNER_OK = True
except Exception as e:
    st.error(f"US Sentiment Scanner: {e}")

try:
    from ai.wall_street_advisor import generate_research_note, generate_from_sentiment, ResearchRating
    from analysis.integrated_analysis import IntegratedAnalysis, compute_composite_score
    from analysis.stock_analyzer import StockAnalyzer
    ADVISOR_OK = True
except Exception as e:
    st.warning(f"Sr. Advisor module: {e}")

for key, default in {
    "us_sentiment_session": None,
    "us_sentiment_preset": "sp500_full",
    "us_last_scan_ts": None,
    "us_sr_note": None,
    "us_sr_ticker": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.markdown("""
<div class="hero">
  <h1>📡 US Market Sentiment</h1>
  <div style="color:#888;font-size:0.88rem;">
    Sweep the US market like a professional trading desk — news sentiment, analyst consensus,
    sector breadth, momentum shifts, and Sr. Wall Street deep research.
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="disc">
  ⚠️ <strong>NOT FINANCIAL ADVICE.</strong> Sentiment data from Yahoo Finance is lagged and imperfect.
  This simulates how desks monitor news flow — it is not a recommendation to trade.
</div>
""", unsafe_allow_html=True)

if not SCANNER_OK:
    st.stop()

# Single-stock lookup (replaces removed AI Sentiment page)
with st.expander("🔎 Single stock — sentiment deep dive", expanded=False):
    tk = st.text_input("Ticker", value="AAPL", key="us_one_ticker").upper().strip()
    if st.button("Analyze ticker", key="us_one_btn") and tk:
        with st.spinner(f"Analyzing {tk}..."):
            try:
                from analysis.sentiment_analyzer import SentimentAnalyzer
                from analysis.stock_analyzer import StockAnalyzer
                tech = StockAnalyzer().analyze(tk)
                sent = SentimentAnalyzer().analyze(tk, tech.current_price if not tech.error else 0)
                c1, c2, c3 = st.columns(3)
                c1.metric("Strategy", tech.signal if not tech.error else "—")
                c2.metric("Tech score", f"{tech.overall_score:.0f}" if not tech.error else "—")
                c3.metric("Sentiment", sent.overall_sentiment_label if sent.is_valid else "—")
                if sent.is_valid:
                    st.markdown(sent.sentiment_summary)
                    if ADVISOR_OK and st.button("Sr. Wall Street note", key="us_one_ws"):
                        note = generate_from_sentiment(
                            sent,
                            technical_score=tech.overall_score if not tech.error else 50,
                            price=tech.current_price if not tech.error else 0,
                            signal=tech.signal if not tech.error else "WATCH",
                            explanation=tech.reason_summary if not tech.error else "",
                        )
                        st.markdown(note.full_report)
            except Exception as ex:
                st.error(str(ex))

# ── Scan controls ─────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>1 · US Market Scan</div>", unsafe_allow_html=True)

preset_keys = list(US_SENTIMENT_PRESETS.keys())
preset_vals = list(US_SENTIMENT_PRESETS.values())
cur_us_preset = st.session_state.get("us_sentiment_preset", "sp500_full")

c1, c2, c3, c4 = st.columns(4)
with c1:
    preset_label = st.selectbox(
        "Universe",
        preset_keys,
        index=preset_vals.index(cur_us_preset) if cur_us_preset in preset_vals else 2,
    )
    preset = US_SENTIMENT_PRESETS[preset_label]
    st.session_state["us_sentiment_preset"] = preset
with c2:
    top_n = st.slider("Top results", 10, 100, 50)
with c3:
    scan_limit = st.number_input(
        "Max tickers to scan",
        50, 500,
        min(DEFAULT_SCAN_LIMIT, 500),
        step=50,
        help="Default 250 — loads automatically; use 500 for full S&P sweep",
    )
with c4:
    workers = st.slider("Parallel workers", 4, 16, 10)

auto_refresh = st.checkbox(
    "Auto-refresh every 5 minutes (background)",
    value=True,
    help="Server refreshes in background; cached results load instantly.",
)
if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=get_ui_poll_seconds() * 1000, key="us_autorefresh")
    except ImportError:
        pass

refresh_col1, refresh_col2 = st.columns([1, 3])
with refresh_col1:
    run_scan = st.button("🔄 Refresh scan now", type="primary", use_container_width=True)

if get_price_bounds(preset) != (None, None):
    st.info(
        "💰 **Price-filter mode** — sweeps US listings and ranks only tickers in the "
        "selected price range (penny / $1–$10 / under $10)."
    )

if run_scan:
    progress = st.progress(0, text="Refreshing US sentiment sweep...")

    def _cb(done, total):
        progress.progress(min(1.0, done / max(1, total)), text=f"Analyzing {done}/{total} tickers...")

    try:
        session, last_ts, scan_status = resolve_us_scan(
            preset=preset,
            limit=int(scan_limit),
            top_n=top_n,
            workers=workers,
            force=True,
            auto_refresh=auto_refresh,
            progress_callback=_cb,
        )
    except Exception as ex:
        progress.empty()
        st.error(str(ex))
        session, last_ts, scan_status = None, None, "missing"
    else:
        progress.empty()
        if session is not None:
            st.session_state["us_sr_note"] = None
            st.success(
                f"✅ Scanned {session.universe_size} tickers in {session.elapsed_seconds}s — "
                f"{session.scanned} with valid data, top {len(session.results)} ranked"
            )
else:
    try:
        session, last_ts, scan_status = resolve_us_scan(
            preset=preset,
            limit=int(scan_limit),
            top_n=top_n,
            workers=workers,
            force=False,
            auto_refresh=auto_refresh,
            progress_callback=None,
        )
    except Exception as ex:
        st.error(str(ex))
        session, last_ts, scan_status = None, None, "missing"

if session is not None:
    st.session_state["us_sentiment_session"] = session
    st.session_state["us_last_scan_ts"] = last_ts
    st.session_state["us_scan_status"] = scan_status

scan_status = st.session_state.get("us_scan_status", scan_status if session else "missing")
with refresh_col2:
    st.caption(
        format_scan_status(
            st.session_state.get("us_last_scan_ts"),
            auto_refresh,
            refreshing=(scan_status == "refreshing"),
        )
    )

if scan_status == "cached":
    st.caption("⚡ Loaded from saved scan — instant on page refresh.")
elif scan_status == "refreshing":
    st.info("🔄 Updating in background — showing last saved market snapshot.")
elif scan_status == "waiting":
    st.info("⏳ First scan running on server — auto-reloads every 30s until ready.")

session = st.session_state.get("us_sentiment_session")

if session and session.results:
    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sh'>2 · Market Breadth — How Real Desks Read the Tape</div>", unsafe_allow_html=True)

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"<div class='mc'><div class='ml'>Universe</div><div class='mv'>{session.universe_size}</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='mc'><div class='ml'>Avg Sentiment</div><div class='mv' style='color:#00E5FF'>{session.avg_sentiment:.0f}</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='mc'><div class='ml'>Bullish %</div><div class='mv' style='color:#00C853'>{session.market_bullish_pct:.0f}%</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='mc'><div class='ml'>Bearish %</div><div class='mv' style='color:#FF1744'>{session.market_bearish_pct:.0f}%</div></div>", unsafe_allow_html=True)
    with m5:
        st.markdown(f"<div class='mc'><div class='ml'>Neutral %</div><div class='mv'>{session.market_neutral_pct:.0f}%</div></div>", unsafe_allow_html=True)

    bc1, bc2 = st.columns(2)
    with bc1:
        fig = go.Figure(go.Pie(
            labels=["Bullish", "Bearish", "Neutral"],
            values=[session.market_bullish_pct, session.market_bearish_pct, session.market_neutral_pct],
            marker_colors=["#00C853", "#FF1744", "#D4AF37"],
            hole=0.45,
        ))
        fig.update_layout(template="plotly_dark", height=280, margin=dict(l=0, r=0, t=20, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", title="Market Sentiment Breadth")
        st.plotly_chart(fig, use_container_width=True)

    with bc2:
        if session.sector_breadth:
            sb = session.sector_breadth[:10]
            fig2 = go.Figure(go.Bar(
                x=[s.sector.replace("_", " ").title() for s in sb],
                y=[s.avg_sentiment for s in sb],
                marker_color=["#00C853" if s.avg_sentiment >= 55 else "#FF1744" if s.avg_sentiment < 45 else "#D4AF37" for s in sb],
            ))
            fig2.update_layout(template="plotly_dark", height=280, margin=dict(l=0, r=0, t=20, b=0),
                               paper_bgcolor="rgba(0,0,0,0)", title="Sector Sentiment (avg)", yaxis_title="Score")
            st.plotly_chart(fig2, use_container_width=True)

    # Sector table
    if session.sector_breadth:
        with st.expander("📊 Sector Breakdown"):
            st.dataframe(pd.DataFrame([
                {
                    "Sector": b.sector.replace("_", " ").title(),
                    "Stocks": b.count,
                    "Avg Sentiment": f"{b.avg_sentiment:.0f}",
                    "Bullish %": f"{b.bullish_pct:.0f}%",
                    "Top Name": b.top_ticker,
                }
                for b in session.sector_breadth
            ]), hide_index=True, use_container_width=True)

    st.markdown("<div class='sh'>3 · Top US Sentiment Leaders</div>", unsafe_allow_html=True)

    rows = []
    for r in session.results:
        rows.append({
            "Rank": r.rank,
            "Ticker": r.ticker,
            "Sector": r.sector.replace("_", " ").title(),
            "Score": f"{r.overall_score:.0f}",
            "Label": r.sentiment_label,
            "News": f"{r.news_score:.0f}",
            "Analyst": r.analyst_recommendation,
            "Momentum": f"{r.sentiment_momentum:+.0f}",
            "Earnings": r.earnings_tone,
            "Buzz": f"{r.social_buzz:.0f}",
            "B/Be Headlines": f"{r.bullish_headlines}/{r.bearish_headlines}",
            "Target Upside": f"{r.price_vs_target_pct:+.1f}%" if r.price_vs_target_pct else "—",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True, height=min(500, 80 + len(df) * 32))

    # Momentum movers
    if session.top_momentum:
        st.markdown("<div class='sh'>4 · Sentiment Momentum Shifts (Recent vs Prior Headlines)</div>", unsafe_allow_html=True)
        mom_rows = [{
            "Ticker": m.ticker,
            "Momentum": f"{m.sentiment_momentum:+.0f}",
            "Score": f"{m.overall_score:.0f}",
            "Label": m.sentiment_label,
            "Sector": m.sector,
        } for m in session.top_momentum[:8]]
        st.dataframe(pd.DataFrame(mom_rows), hide_index=True, use_container_width=True)

    # Sr Wall Street deep dive
    if ADVISOR_OK:
        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
        st.markdown("<div class='sh'>5 · 🏛️ Sr. Wall Street Advisor — Deep Research</div>", unsafe_allow_html=True)

        tickers = [r.ticker for r in session.results]
        sel = st.selectbox("Select ticker for full research note", tickers, key="us_sr_select")
        deep_btn = st.button("Generate Sr. Advisor Research Note", type="primary")

        if deep_btn and sel:
            with st.spinner(f"Generating institutional research on {sel}..."):
                try:
                    row = next(r for r in session.results if r.ticker == sel)
                    tech_score = 55.0
                    explanation = ""
                    try:
                        analysis = StockAnalyzer().analyze(sel)
                        if not analysis.error:
                            tech_score = analysis.overall_score
                            explanation = analysis.explanation
                    except Exception:
                        pass

                    if row.raw:
                        note = generate_from_sentiment(
                            row.raw,
                            technical_score=tech_score,
                            price=row.price,
                            signal="WATCH",
                            explanation=explanation,
                        )
                    else:
                        integrated = IntegratedAnalysis(
                            ticker=sel, price=row.price,
                            technical_score=tech_score,
                            sentiment_score=row.overall_score,
                            news_score=row.news_score,
                            composite_score=row.overall_score,
                            signal="WATCH", explanation=explanation,
                            sector=row.sector,
                        )
                        note = generate_research_note(integrated)

                    st.session_state["us_sr_note"] = note
                    st.session_state["us_sr_ticker"] = sel
                except Exception as ex:
                    st.error(f"Research generation failed: {ex}")

        note = st.session_state.get("us_sr_note")
        if note and st.session_state.get("us_sr_ticker"):
            rating_color = {
                ResearchRating.HIGHLY_ATTRACTIVE: "#00C853",
                ResearchRating.ATTRACTIVE: "#69F0AE",
                ResearchRating.NEUTRAL: "#D4AF37",
                ResearchRating.UNATTRACTIVE: "#FFA726",
                ResearchRating.HIGH_RISK: "#FF1744",
            }.get(note.rating, "#888")
            st.markdown(
                f"**{note.ticker}** — Rating: "
                f"<span style='color:{rating_color};font-weight:800'>{note.rating.value}</span> | "
                f"Conviction: **{note.conviction_score:.0f}/100**",
                unsafe_allow_html=True,
            )
            st.markdown(note.full_report)

            row = next((r for r in session.results if r.ticker == note.ticker), None)
            if row and row.raw and row.raw.news_items:
                with st.expander(f"📰 All headlines — {note.ticker}"):
                    for n in row.raw.news_items[:12]:
                        css = "news-bull" if n.sentiment_label == "BULLISH" else (
                            "news-bear" if n.sentiment_label == "BEARISH" else "news-neut"
                        )
                        st.markdown(
                            f"<div class='{css}'><strong>{n.sentiment_label}</strong> {n.title}"
                            f"<br><span style='font-size:0.75rem;color:#666;'>{n.source}</span></div>",
                            unsafe_allow_html=True,
                        )

else:
    st.info(
        "Scan in progress or no results yet — try **Refresh scan now** or wait for auto-refresh."
    )

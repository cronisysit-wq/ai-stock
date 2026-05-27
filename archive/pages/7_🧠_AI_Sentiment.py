"""
AI Analysis & Sentiment — per-stock deep dive combining:
  - Technical indicators
  - News headline sentiment
  - Analyst consensus
  - 52-week positioning
  - Fundamental data (PE, growth, beta, short interest)
  - Market context (SPY trend, VIX proxy)
  - AI narrative (Gemini if configured, rule-based otherwise)

NOT FINANCIAL ADVICE.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="AI Analysis & Sentiment | AI Trading Assistant",
    page_icon="🧠",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--gold:#D4AF37;--cyan:#00E5FF;--green:#00C853;--red:#FF1744;--amber:#FFA726;
      --glass:rgba(16,16,36,0.88);--border:rgba(212,175,55,0.14);--bg:#06060F;}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:var(--bg);}
.hero{background:linear-gradient(135deg,rgba(0,229,255,0.07),rgba(212,175,55,0.06),rgba(0,200,83,0.05));
  border:1px solid rgba(0,229,255,0.18);border-radius:16px;padding:1.4rem 1.8rem;margin-bottom:1.2rem;
  position:relative;overflow:hidden;}
.hero::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,#00E5FF,#D4AF37,#00C853);}
.hero-title{font-size:2rem;font-weight:900;
  background:linear-gradient(135deg,#00E5FF,#D4AF37,#00C853);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0 0 0.25rem;}
.disc{background:rgba(255,167,38,0.06);border:1px solid rgba(255,167,38,0.28);
  border-left:4px solid #FFA726;border-radius:10px;padding:0.7rem 1rem;
  margin-bottom:1.1rem;color:#FFA726;font-size:0.81rem;font-weight:600;line-height:1.5;}
.sh{font-size:0.9rem;font-weight:800;color:var(--gold);text-transform:uppercase;
  letter-spacing:2px;padding-bottom:0.4rem;margin-bottom:0.8rem;
  border-bottom:1px solid rgba(212,175,55,0.18);}
.card{background:var(--glass);backdrop-filter:blur(18px);border:1px solid var(--border);
  border-radius:14px;padding:1.1rem 1.3rem;margin-bottom:0.8rem;
  position:relative;overflow:hidden;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--cyan),transparent);}
.mc{background:rgba(0,229,255,0.04);border:1px solid rgba(0,229,255,0.1);
  border-radius:10px;padding:0.7rem 0.9rem;text-align:center;}
.ml{font-size:0.6rem;font-weight:700;text-transform:uppercase;letter-spacing:1.3px;color:#555;margin-bottom:0.2rem;}
.mv{font-size:1.3rem;font-weight:900;color:#fff;font-family:'JetBrains Mono',monospace;}
.gd{height:1px;background:linear-gradient(90deg,transparent,#00E5FF,transparent);margin:1.1rem 0;border:none;}
.news-bull{background:rgba(0,200,83,0.08);border-left:3px solid #00C853;
  border-radius:0 8px 8px 0;padding:0.5rem 0.8rem;margin-bottom:0.4rem;}
.news-bear{background:rgba(255,23,68,0.08);border-left:3px solid #FF1744;
  border-radius:0 8px 8px 0;padding:0.5rem 0.8rem;margin-bottom:0.4rem;}
.news-neut{background:rgba(212,175,55,0.05);border-left:3px solid #555;
  border-radius:0 8px 8px 0;padding:0.5rem 0.8rem;margin-bottom:0.4rem;}
.sent-bull{color:#00C853;font-weight:800;}
.sent-bear{color:#FF1744;font-weight:800;}
.sent-neut{color:#D4AF37;font-weight:700;}
.ai-badge{display:inline-block;background:linear-gradient(135deg,rgba(0,229,255,0.15),rgba(212,175,55,0.1));
  border:1px solid rgba(0,229,255,0.3);border-radius:20px;padding:0.2rem 0.8rem;
  font-size:0.72rem;font-weight:700;color:#00E5FF;letter-spacing:0.5px;margin-bottom:0.6rem;}
.rule-badge{display:inline-block;background:rgba(212,175,55,0.08);
  border:1px solid rgba(212,175,55,0.2);border-radius:20px;padding:0.2rem 0.8rem;
  font-size:0.72rem;font-weight:700;color:#D4AF37;letter-spacing:0.5px;margin-bottom:0.6rem;}
.score-bg{background:rgba(255,255,255,0.05);border-radius:6px;height:9px;overflow:hidden;margin-top:0.2rem;}
.stTabs [data-baseweb="tab-list"]{gap:5px;}
.stTabs [data-baseweb="tab"]{background:rgba(16,16,36,0.6);border:1px solid rgba(0,229,255,0.08);
  border-radius:8px 8px 0 0;padding:8px 16px;color:#888;font-weight:600;font-size:0.88rem;}
.stTabs [aria-selected="true"]{background:rgba(0,229,255,0.08)!important;
  border-bottom:2px solid #00E5FF!important;color:#00E5FF!important;}
</style>
""", unsafe_allow_html=True)

# ── Imports ────────────────────────────────────────────────────────────────────
SETTINGS_OK = False
try:
    from db.database import init_db
    from config.settings import get_settings
    init_db()
    settings = get_settings()
    SETTINGS_OK = True
except Exception:
    settings = None

SENTIMENT_OK = False
try:
    from analysis.sentiment_analyzer import SentimentAnalyzer, SentimentResult
    SENTIMENT_OK = True
except Exception as e:
    st.error(f"Sentiment module: {e}")

ANALYST_OK = False
try:
    from ai.analyst import (
        explain_stock_analysis, explain_scan_result,
        explain_sentiment_context, explain_ranking_comparison,
        is_ai_available, AnalystResponse,
    )
    ANALYST_OK = True
except Exception as e:
    st.error(f"AI analyst: {e}")

SCANNER_OK = False
try:
    from analysis.market_scanner import MarketScanner
    SCANNER_OK = True
except Exception:
    pass

RANKER_OK = False
try:
    from analysis.stock_ranker import StockRanker
    RANKER_OK = True
except Exception:
    pass

ADVISOR_OK = False
try:
    from ai.institutional_advisor import (
        AdvisorPersona, PERSONA_LABELS, explain_integrated, DAILY_TARGET_PRESETS,
    )
    from analysis.integrated_analysis import IntegratedAnalysis, compute_composite_score
    ADVISOR_OK = True
except Exception:
    pass

WS_ADVISOR_OK = False
try:
    from ai.wall_street_advisor import generate_research_note, generate_from_sentiment
    WS_ADVISOR_OK = True
except Exception:
    pass

if "ai_advisor_persona" not in st.session_state:
    st.session_state["ai_advisor_persona"] = AdvisorPersona.BUFFETT if ADVISOR_OK else "warren_buffett"
if "ai_daily_target_pct" not in st.session_state:
    st.session_state["ai_daily_target_pct"] = 0.75

# ── Helpers ────────────────────────────────────────────────────────────────────
def _sentiment_color(label: str) -> str:
    return {"BULLISH": "#00C853", "BEARISH": "#FF1744", "NEUTRAL": "#D4AF37"}.get(label, "#888")

def _sentiment_emoji(label: str) -> str:
    return {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}.get(label, "⚪")

def _gauge_chart(value: float, title: str, color: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title, "font": {"size": 13, "color": "#888", "family": "Inter"}},
        number={"font": {"size": 28, "color": "#fff", "family": "JetBrains Mono"}, "suffix": "/100"},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#333", "tickwidth": 1},
            "bar": {"color": color, "thickness": 0.3},
            "bgcolor": "rgba(255,255,255,0.04)",
            "bordercolor": "rgba(255,255,255,0.08)",
            "steps": [
                {"range": [0, 35], "color": "rgba(255,23,68,0.1)"},
                {"range": [35, 65], "color": "rgba(212,175,55,0.08)"},
                {"range": [65, 100], "color": "rgba(0,200,83,0.1)"},
            ],
            "threshold": {"line": {"color": color, "width": 3}, "thickness": 0.8, "value": value},
        }
    ))
    fig.update_layout(
        height=180, margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", font={"color": "#aaa"},
    )
    return fig

# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class='hero'>
  <div class='hero-title'>🧠 AI Analysis & Sentiment</div>
  <div style='color:#666;font-size:0.86rem;'>
    Real news sentiment · Analyst consensus · Fundamental data · Market context ·
    AI narrative (Gemini when configured) · Not financial advice
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class='disc'>
  ⚠️ <strong>NOT FINANCIAL ADVICE.</strong> Sentiment analysis and AI explanations are educational tools only.
  Sentiment scores are based on headline keywords and may not reflect actual market conditions.
  Analyst targets are third-party opinions. Past patterns do not predict future results.
</div>
""", unsafe_allow_html=True)

# ── AI status banner ──────────────────────────────────────────────────────────
if ANALYST_OK:
    ai_live = is_ai_available()
    if ai_live:
        st.success("🤖 **Gemini AI Active** — Real AI analysis enabled. Set GEMINI_API_KEY in .env to enable.")
    else:
        st.info(
            "📊 **Rule-based mode** — Add `GEMINI_API_KEY=your_key` to your `.env` file to enable real "
            "[Google Gemini AI](https://aistudio.google.com/app/apikey) analysis (free tier available)."
        )

# ── Ticker input ───────────────────────────────────────────────────────────────
st.markdown("<div class='sh'>🔎 Stock Analysis Input</div>", unsafe_allow_html=True)

if ADVISOR_OK:
    ap1, ap2 = st.columns(2)
    with ap1:
        persona_keys = list(PERSONA_LABELS.keys())
        cur = st.session_state.get("ai_advisor_persona", AdvisorPersona.BUFFETT)
        if cur not in persona_keys:
            cur = AdvisorPersona.BUFFETT
        sel = st.selectbox(
            "Institutional AI persona",
            range(len(persona_keys)),
            format_func=lambda i: PERSONA_LABELS[persona_keys[i]],
            index=persona_keys.index(cur),
            key="ai_persona_select",
        )
        st.session_state["ai_advisor_persona"] = persona_keys[sel]
    with ap2:
        preset = st.selectbox("Daily target preset (reference)", list(DAILY_TARGET_PRESETS.keys()), key="ai_target_preset")
        if DAILY_TARGET_PRESETS[preset] > 0:
            st.session_state["ai_daily_target_pct"] = DAILY_TARGET_PRESETS[preset]
        st.session_state["ai_daily_target_pct"] = st.number_input(
            "Daily target % (reference)", 0.25, 25.0,
            float(st.session_state["ai_daily_target_pct"]), 0.25, format="%.2f",
        )

col_in1, col_in2, col_in3 = st.columns([3, 1, 1])
with col_in1:
    ticker_input = st.text_input(
        "Enter ticker(s) — comma-separated for comparison",
        value="AAPL",
        key="ai_ticker_input",
        label_visibility="collapsed",
        placeholder="e.g. AAPL, MSFT, NVDA",
    )
with col_in2:
    include_sentiment = st.checkbox("📰 News & Sentiment", value=True, key="incl_sent")
with col_in3:
    run_btn = st.button("🔍 Analyze", type="primary", use_container_width=True, key="ai_run_btn")

# ── Run analysis ───────────────────────────────────────────────────────────────
if "ai_results" not in st.session_state:
    st.session_state["ai_results"] = {}

if run_btn:
    tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
    if not tickers:
        st.warning("Enter at least one ticker.")
    elif len(tickers) > 6:
        st.warning("Maximum 6 tickers for AI analysis (each requires multiple API calls).")
    else:
        results = {}
        progress = st.progress(0, text="Initializing...")
        sentiment_analyzer = SentimentAnalyzer() if SENTIMENT_OK else None
        ranker = StockRanker(max_workers=6) if RANKER_OK else None

        for i, ticker in enumerate(tickers):
            progress.progress((i + 0.3) / len(tickers), text=f"Analyzing {ticker} — technical indicators...")
            tech_result = None
            sent_result = None
            ai_response = None

            # Technical analysis
            if ranker:
                try:
                    rank_session = ranker.rank([ticker])
                    tech_result = rank_session.ranked[0] if rank_session.ranked else None
                except Exception as e:
                    st.warning(f"Technical analysis failed for {ticker}: {e}")

            # Sentiment
            if include_sentiment and sentiment_analyzer:
                progress.progress((i + 0.6) / len(tickers), text=f"Fetching sentiment & news for {ticker}...")
                try:
                    price = tech_result.price if tech_result else 0.0
                    sent_result = sentiment_analyzer.analyze(ticker, current_price=price)
                except Exception as e:
                    st.warning(f"Sentiment fetch failed for {ticker}: {e}")

            # AI explanation
            if ANALYST_OK and tech_result:
                progress.progress((i + 0.85) / len(tickers), text=f"Generating AI explanation for {ticker}...")
                try:
                    ai_response = explain_stock_analysis(tech_result.analysis, sentiment=sent_result)
                except Exception as e:
                    st.warning(f"AI explanation failed for {ticker}: {e}")

            results[ticker] = {
                "tech": tech_result,
                "sentiment": sent_result,
                "ai": ai_response,
            }

        progress.progress(1.0, text="✅ Complete!")
        import time
        time.sleep(0.4)
        progress.empty()
        st.session_state["ai_results"] = results
        st.success(f"✅ Analyzed {len(results)} ticker(s).")

# ── Display results ────────────────────────────────────────────────────────────
results = st.session_state.get("ai_results", {})

if not results:
    st.markdown("""
    <div style='text-align:center;padding:3rem;color:#555;'>
      <div style='font-size:3rem;'>🧠</div>
      <div style='margin-top:0.8rem;font-size:1.1rem;font-weight:700;color:#777;'>Enter a ticker and click Analyze</div>
      <div style='margin-top:0.4rem;font-size:0.85rem;'>
        You'll see: news sentiment, analyst consensus, key fundamentals,<br>
        market context, and AI-powered narrative explanation.
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    tickers_analyzed = list(results.keys())

    # Comparison bar if multiple
    if len(tickers_analyzed) > 1:
        st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
        st.markdown("<div class='sh'>⚖️ Side-by-Side Comparison</div>", unsafe_allow_html=True)
        comp_rows = []
        for tk, data in results.items():
            tech = data.get("tech")
            sent = data.get("sentiment")
            comp_rows.append({
                "Ticker": tk,
                "Price": f"${tech.price:,.2f}" if tech else "N/A",
                "Signal": tech.analysis.signal if tech else "N/A",
                "Tech Score": f"{tech.overall_score:.0f}/100" if tech else "N/A",
                "Sentiment": f"{sent.overall_sentiment_label} ({sent.overall_sentiment_score:.0f})" if sent and sent.is_valid else "N/A",
                "Analyst": sent.analyst_recommendation if sent and sent.is_valid else "N/A",
                "News": f"🟢 {sent.bullish_headlines}B / 🔴 {sent.bearish_headlines}Be" if sent and sent.is_valid else "N/A",
                "Target Upside": f"{sent.price_vs_target_pct:+.1f}%" if sent and sent.is_valid and sent.price_vs_target_pct else "N/A",
                "Risk": f"{tech.analysis.risk_score:.0f}/100" if tech else "N/A",
                "AI Tier": "🤖 Gemini" if (data.get("ai") and data["ai"].ai_powered) else "📊 Rule-based",
            })
        comp_df = pd.DataFrame(comp_rows)
        def _clr_sig(v):
            return {"BUY_CANDIDATE":"color:#00C853;font-weight:800;","WATCH":"color:#D4AF37;","AVOID":"color:#888;","SELL_CANDIDATE":"color:#FF1744;"}.get(str(v),"")
        st.dataframe(
            comp_df.style.map(_clr_sig, subset=["Signal"]),
            use_container_width=True, hide_index=True
        )

        # AI comparison
        if ANALYST_OK and len(tickers_analyzed) >= 2:
            with st.expander("🤖 AI Ranking Comparison", expanded=False):
                try:
                    ranked_list = [results[tk]["tech"] for tk in tickers_analyzed if results[tk].get("tech")]
                    ranked_list_sorted = sorted(ranked_list, key=lambda r: r.overall_score, reverse=True)
                    comp_text = explain_ranking_comparison(ranked_list_sorted)
                    st.markdown(comp_text)
                except Exception as e:
                    st.caption(f"Comparison unavailable: {e}")

    # Per-ticker detail tabs
    if len(tickers_analyzed) > 1:
        ticker_tabs = st.tabs([f"📊 {tk}" for tk in tickers_analyzed])
    else:
        ticker_tabs = [st]

    for tab_obj, ticker in zip(ticker_tabs, tickers_analyzed):
        data = results[ticker]
        tech: "RankedStock" = data.get("tech")
        sent: "SentimentResult" = data.get("sentiment")
        ai: "AnalystResponse" = data.get("ai")

        with tab_obj if len(tickers_analyzed) > 1 else st.container():
            st.markdown("<div class='gd'></div>", unsafe_allow_html=True)

            # ── Header row ────────────────────────────────────────────────────
            if tech:
                a = tech.analysis
                h1, h2, h3 = st.columns([2, 3, 2])
                with h1:
                    chg_c = "#00C853" if (a.indicators.get("rsi") or 50) > 50 else "#FF1744"
                    st.markdown(f"""
                    <div class='card'>
                      <div style='font-size:2rem;font-weight:900;color:#D4AF37;'>{ticker}</div>
                      <div style='font-size:1.4rem;font-weight:900;color:#fff;font-family:JetBrains Mono,monospace;'>${a.current_price:,.2f}</div>
                      <div style='margin-top:0.4rem;font-size:0.78rem;'>
                        <span style='color:#888;'>Signal:</span>
                        <strong style='color:{"#00C853" if a.signal=="BUY_CANDIDATE" else "#FF1744" if a.signal=="SELL_CANDIDATE" else "#D4AF37"};'>
                          {a.signal}
                        </strong>
                      </div>
                      <div style='font-size:0.78rem;color:#666;margin-top:0.3rem;'>
                        Tech Score: <strong style='color:#fff;'>{a.overall_score:.0f}/100</strong> |
                        Risk: <strong style='color:#FFA726;'>{a.risk_score:.0f}/100</strong>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                with h2:
                    # Gauge charts
                    g1, g2, g3 = st.columns(3)
                    with g1:
                        st.plotly_chart(_gauge_chart(a.overall_score, "Tech Score", "#D4AF37"), use_container_width=True, config={"displayModeBar": False})
                    with g2:
                        sent_score = sent.overall_sentiment_score if sent and sent.is_valid else 50.0
                        st.plotly_chart(_gauge_chart(sent_score, "Sentiment", "#00E5FF"), use_container_width=True, config={"displayModeBar": False})
                    with g3:
                        risk_inv = 100 - a.risk_score
                        st.plotly_chart(_gauge_chart(risk_inv, "Safety Score", "#00C853"), use_container_width=True, config={"displayModeBar": False})

                with h3:
                    if sent and sent.is_valid:
                        st.markdown(f"""
                        <div class='card'>
                          <div style='font-size:0.6rem;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:0.6rem;'>Analyst & Fundamentals</div>
                          <div style='margin-bottom:0.35rem;display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>Analyst</span>
                            <strong style='color:{"#00C853" if "BUY" in sent.analyst_recommendation else "#FF1744" if "SELL" in sent.analyst_recommendation else "#D4AF37"};font-size:0.78rem;'>{sent.analyst_recommendation}</strong>
                          </div>
                          <div style='margin-bottom:0.35rem;display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>Target Price</span>
                            <span style='color:#fff;font-family:JetBrains Mono;font-size:0.78rem;'>${sent.analyst_target_price:,.2f} ({sent.price_vs_target_pct:+.1f}%)</span>
                          </div>
                          <div style='margin-bottom:0.35rem;display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>52w High</span>
                            <span style='color:#fff;font-family:JetBrains Mono;font-size:0.78rem;'>${sent.week_52_high:,.2f} ({sent.price_vs_52w_high_pct:+.1f}%)</span>
                          </div>
                          <div style='margin-bottom:0.35rem;display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>Beta</span>
                            <span style='color:#CE93D8;font-family:JetBrains Mono;font-size:0.78rem;'>{sent.beta or "N/A"}</span>
                          </div>
                          <div style='margin-bottom:0.35rem;display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>Short Ratio</span>
                            <span style='color:#FFA726;font-family:JetBrains Mono;font-size:0.78rem;'>{f"{sent.short_ratio:.1f}d" if sent.short_ratio else "N/A"}</span>
                          </div>
                          <div style='display:flex;justify-content:space-between;'>
                            <span style='color:#888;font-size:0.78rem;'>Market Trend</span>
                            <span style='color:{"#00C853" if sent.market_trend=="BULLISH" else "#FF1744" if sent.market_trend=="BEARISH" else "#D4AF37"};font-weight:700;font-size:0.78rem;'>{sent.market_trend}</span>
                          </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("Enable 'News & Sentiment' checkbox to see fundamental data.")

            # ── Inner tabs ────────────────────────────────────────────────────
            itab_ai, itab_ws, itab_sent, itab_news, itab_tech = st.tabs([
                "🤖 AI Analysis", "🏛️ Sr. Wall Street", "📊 Sentiment Detail", "📰 News Headlines", "📈 Technical"
            ])

            # ── AI Tab ────────────────────────────────────────────────────────
            with itab_ai:
                if ai:
                    badge = "ai-badge" if ai.ai_powered else "rule-badge"
                    tier_text = "🤖 Gemini AI" if ai.ai_powered else "📊 Rule-Based"
                    st.markdown(f"<span class='{badge}'>{tier_text}</span>", unsafe_allow_html=True)
                    st.markdown(ai.explanation)
                    st.markdown(ai.disclaimer)
                elif not ANALYST_OK:
                    st.error("AI analyst not available.")
                else:
                    st.info("Run analysis to see AI explanation.")

                # Sentiment AI narrative
                if sent and sent.is_valid and ANALYST_OK:
                    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
                    st.markdown("**Sentiment Context Explanation**")
                    with st.spinner("Generating sentiment narrative..."):
                        try:
                            sent_ai = explain_sentiment_context(sent)
                            st.markdown(f"<span class='{'ai-badge' if sent_ai.ai_powered else 'rule-badge'}'>{'🤖 Gemini' if sent_ai.ai_powered else '📊 Rule-Based'}</span>", unsafe_allow_html=True)
                            st.markdown(sent_ai.explanation)
                        except Exception as e:
                            st.caption(f"Unavailable: {e}")

                if ADVISOR_OK and tech and sent and sent.is_valid:
                    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
                    st.markdown("**🏛️ Institutional Advisor (News + Sentiment + Technicals)**")
                    try:
                        composite = compute_composite_score(
                            tech.overall_score,
                            sent.overall_sentiment_score,
                            sent.news_sentiment_score,
                        )
                        integrated = IntegratedAnalysis(
                            ticker=ticker,
                            price=tech.price,
                            technical_score=tech.overall_score,
                            sentiment_score=sent.overall_sentiment_score,
                            news_score=sent.news_sentiment_score,
                            composite_score=composite,
                            signal=tech.analysis.signal,
                            explanation=tech.analysis.explanation,
                            sentiment=sent,
                            news_headlines=sent.news_items[:8],
                            sentiment_label=sent.overall_sentiment_label,
                            analyst_consensus=sent.analyst_recommendation,
                            catalyst_notes=sent.catalyst_notes,
                        )
                        inst = explain_integrated(
                            integrated,
                            st.session_state.get("ai_advisor_persona", AdvisorPersona.BUFFETT),
                            st.session_state.get("ai_daily_target_pct", 0.75),
                            25000.0,
                        )
                        st.markdown(inst.full_text)
                    except Exception as e:
                        st.caption(f"Institutional advisor: {e}")

            # ── Sr Wall Street Tab ─────────────────────────────────────────────
            with itab_ws:
                if WS_ADVISOR_OK and tech and sent and sent.is_valid:
                    if st.button(f"Generate Sr. Research Note — {ticker}", key=f"ws_btn_{ticker}"):
                        with st.spinner("Building institutional research note..."):
                            try:
                                ws_note = generate_from_sentiment(
                                    sent,
                                    technical_score=tech.overall_score,
                                    price=tech.price,
                                    signal=tech.analysis.signal,
                                    explanation=tech.analysis.explanation,
                                    account_equity=25000.0,
                                    daily_target_pct=st.session_state.get("ai_daily_target_pct", 0.75),
                                )
                                st.session_state[f"ws_note_{ticker}"] = ws_note
                            except Exception as e:
                                st.error(str(e))
                    ws_note = st.session_state.get(f"ws_note_{ticker}")
                    if ws_note:
                        st.markdown(ws_note.full_report)
                    else:
                        st.info(
                            "Click **Generate Sr. Research Note** for a full sell-side-style briefing: "
                            "thesis, bull/bear case, risks, catalysts, and verdict — like a Sr. Wall Street advisor."
                        )
                else:
                    st.info("Run full analysis with News & Sentiment enabled to unlock Sr. Wall Street research.")

            # ── Sentiment Tab ──────────────────────────────────────────────────
            with itab_sent:
                if sent and sent.is_valid:
                    s1, s2, s3 = st.columns(3)
                    with s1:
                        color = _sentiment_color(sent.news_sentiment_label)
                        emoji = _sentiment_emoji(sent.news_sentiment_label)
                        st.markdown(f"<div class='mc'><div class='ml'>News Sentiment</div><div class='mv' style='color:{color};'>{emoji} {sent.news_sentiment_label}</div></div>", unsafe_allow_html=True)
                    with s2:
                        color = _sentiment_color(sent.analyst_recommendation.replace("STRONG ","") if sent.analyst_recommendation != "N/A" else "NEUTRAL")
                        st.markdown(f"<div class='mc'><div class='ml'>Analyst Consensus</div><div class='mv' style='color:{"#00C853" if "BUY" in sent.analyst_recommendation else "#FF1744" if "SELL" in sent.analyst_recommendation else "#D4AF37"};'>{sent.analyst_recommendation}</div></div>", unsafe_allow_html=True)
                    with s3:
                        color = _sentiment_color(sent.overall_sentiment_label)
                        st.markdown(f"<div class='mc'><div class='ml'>Overall Sentiment</div><div class='mv' style='color:{color};'>{sent.overall_sentiment_score:.0f}/100</div></div>", unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(sent.sentiment_summary)

                    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
                    st.markdown("**📅 Detected Catalysts**")
                    st.markdown(sent.catalyst_notes)

                    # Key fundamentals table
                    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
                    st.markdown("**📊 Key Fundamentals (from Yahoo Finance)**")
                    fund_data = {
                        "Metric": ["PE Ratio", "Forward PE", "Price/Book", "Beta", "Market Cap",
                                   "Div. Yield", "Earnings Growth YoY", "Revenue Growth YoY",
                                   "Short Ratio", "52w High", "52w Low", "Price vs Target"],
                        "Value": [
                            f"{sent.pe_ratio:.1f}" if sent.pe_ratio else "N/A",
                            f"{sent.forward_pe:.1f}" if sent.forward_pe else "N/A",
                            f"{sent.price_to_book:.2f}" if sent.price_to_book else "N/A",
                            f"{sent.beta:.2f}" if sent.beta else "N/A",
                            f"${sent.market_cap/1e9:.1f}B" if sent.market_cap else "N/A",
                            f"{sent.dividend_yield*100:.2f}%" if sent.dividend_yield else "N/A",
                            f"{sent.earnings_growth*100:.1f}%" if sent.earnings_growth else "N/A",
                            f"{sent.revenue_growth*100:.1f}%" if sent.revenue_growth else "N/A",
                            f"{sent.short_ratio:.1f} days" if sent.short_ratio else "N/A",
                            f"${sent.week_52_high:,.2f}" if sent.week_52_high else "N/A",
                            f"${sent.week_52_low:,.2f}" if sent.week_52_low else "N/A",
                            f"{sent.price_vs_target_pct:+.1f}%" if sent.price_vs_target_pct else "N/A",
                        ]
                    }
                    st.dataframe(pd.DataFrame(fund_data), use_container_width=True, hide_index=True, height=420)
                else:
                    st.info("Enable 'News & Sentiment' and re-run to see sentiment data.")

            # ── News Tab ──────────────────────────────────────────────────────
            with itab_news:
                if sent and sent.is_valid and sent.news_items:
                    bull_ct = sent.bullish_headlines
                    bear_ct = sent.bearish_headlines
                    neut_ct = len(sent.news_items) - bull_ct - bear_ct

                    nc1, nc2, nc3, nc4 = st.columns(4)
                    with nc1: st.markdown(f"<div class='mc'><div class='ml'>Total Headlines</div><div class='mv'>{len(sent.news_items)}</div></div>", unsafe_allow_html=True)
                    with nc2: st.markdown(f"<div class='mc'><div class='ml'>Bullish</div><div class='mv' style='color:#00C853;'>{bull_ct}</div></div>", unsafe_allow_html=True)
                    with nc3: st.markdown(f"<div class='mc'><div class='ml'>Bearish</div><div class='mv' style='color:#FF1744;'>{bear_ct}</div></div>", unsafe_allow_html=True)
                    with nc4: st.markdown(f"<div class='mc'><div class='ml'>News Score</div><div class='mv' style='color:#00E5FF;'>{sent.news_sentiment_score:.0f}/100</div></div>", unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)
                    for item in sent.news_items:
                        css_cls = "news-bull" if item.sentiment_label == "BULLISH" else "news-bear" if item.sentiment_label == "BEARISH" else "news-neut"
                        sent_class = "sent-bull" if item.sentiment_label == "BULLISH" else "sent-bear" if item.sentiment_label == "BEARISH" else "sent-neut"
                        kws = " ".join(f"`{k}`" for k in item.keywords_found[:3]) if item.keywords_found else ""
                        url_html = f" | <a href='{item.url}' target='_blank' style='color:#555;font-size:0.7rem;'>🔗 link</a>" if item.url else ""
                        st.markdown(f"""
                        <div class='{css_cls}'>
                          <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
                            <div style='font-size:0.82rem;font-weight:600;color:#ddd;flex:1;'>{item.title}</div>
                            <span class='{sent_class}' style='font-size:0.7rem;margin-left:0.8rem;white-space:nowrap;'>{item.sentiment_label} ({item.sentiment_score:+.0f})</span>
                          </div>
                          <div style='font-size:0.68rem;color:#555;margin-top:0.2rem;'>{item.source} · {item.published}{url_html}</div>
                          {'<div style="font-size:0.68rem;color:#444;margin-top:0.15rem;">Keywords: ' + kws + '</div>' if kws else ''}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Enable 'News & Sentiment' and re-run to see live headlines.")

            # ── Technical Tab ──────────────────────────────────────────────────
            with itab_tech:
                if tech:
                    a = tech.analysis
                    t1, t2 = st.columns(2)
                    with t1:
                        score_data = {
                            "Dimension": ["Trend", "Momentum", "Volume", "Risk (lower=better)"],
                            "Score": [a.trend_score, a.momentum_score, a.volume_score, 100-a.risk_score],
                        }
                        fig_radar = go.Figure(go.Bar(
                            x=score_data["Score"], y=score_data["Dimension"],
                            orientation="h",
                            marker=dict(color=["#D4AF37","#CE93D8","#FFA726","#00C853"],opacity=0.85),
                        ))
                        fig_radar.update_layout(
                            height=220, template="plotly_dark", margin=dict(l=0,r=0,t=10,b=0),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(16,16,36,0.5)",
                            xaxis=dict(range=[0,100], gridcolor="rgba(255,255,255,0.05)"),
                        )
                        st.plotly_chart(fig_radar, use_container_width=True, config={"displayModeBar":False})

                    with t2:
                        ind = a.indicators
                        tech_table = {
                            "Indicator": ["RSI(14)", "MACD Hist.", "SMA20", "SMA50",
                                         "ATR%", "Volume Ratio", "BB Position", "Support", "Resistance"],
                            "Value": [
                                f"{ind.get('rsi','N/A'):.1f}" if isinstance(ind.get('rsi'), float) else "N/A",
                                f"{ind.get('macd_hist','N/A'):.4f}" if isinstance(ind.get('macd_hist'), float) else "N/A",
                                f"${ind.get('sma_20','N/A'):,.2f}" if isinstance(ind.get('sma_20'), float) else "N/A",
                                f"${ind.get('sma_50','N/A'):,.2f}" if isinstance(ind.get('sma_50'), float) else "N/A",
                                f"{ind.get('atr_pct','N/A'):.2f}%" if isinstance(ind.get('atr_pct'), float) else "N/A",
                                f"{ind.get('volume_ratio','N/A'):.2f}x" if isinstance(ind.get('volume_ratio'), float) else "N/A",
                                f"{ind.get('bb_position','N/A'):.2f}" if isinstance(ind.get('bb_position'), float) else "N/A",
                                f"${a.support_level:,.2f}",
                                f"${a.resistance_level:,.2f}",
                            ]
                        }
                        st.dataframe(pd.DataFrame(tech_table), use_container_width=True, hide_index=True, height=320)

                    st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
                    st.markdown(f"**Strategy summary:** {a.reason_summary}")
                    st.markdown(f"**Timeframe bias:** {a.timeframe_bias.replace('_', '-')} | **Signal:** {a.signal}")
                else:
                    st.info("Technical analysis not available for this ticker.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("<div class='gd'></div>", unsafe_allow_html=True)
st.markdown("""
<div style='font-size:0.7rem;color:#333;text-align:center;line-height:1.8;'>
  ⚠️ NOT FINANCIAL ADVICE. AI analysis is educational only. News sentiment scores are keyword-based approximations.
  Analyst targets are third-party opinions. Technical indicators do not guarantee future performance.<br>
  To enable real AI: add <code>GEMINI_API_KEY=your_key</code> to <code>.env</code> — free at
  <a href='https://aistudio.google.com/app/apikey' target='_blank' style='color:#555;'>aistudio.google.com</a>
</div>
""", unsafe_allow_html=True)

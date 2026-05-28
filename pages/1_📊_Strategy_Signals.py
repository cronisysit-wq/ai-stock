"""
Strategy Signals — all stocks ranked by strategy + sentiment in one table.
STRONG BUY rows always appear at the top. Live prices when available.

NOT FINANCIAL ADVICE.
"""

import streamlit as st
import pandas as pd
import time as _time

from ui.auto_scan import (
    DEFAULT_SCAN_LIMIT,
    get_ui_poll_seconds,
    format_scan_status,
)
from ui.scan_service import resolve_strategy_scan

st.set_page_config(page_title="Strategy Signals", page_icon="📊", layout="wide")

st.markdown("""
<style>
html,body,[class*="css"]{font-family:Inter,sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:#0a0a12;}
h1{color:#D4AF37;font-size:1.6rem;margin-bottom:0.2rem;}
.sub{color:#888;font-size:0.85rem;margin-bottom:1rem;}
.disc{background:rgba(255,167,38,0.08);border-left:3px solid #FFA726;padding:0.6rem 0.9rem;
  font-size:0.8rem;color:#FFA726;margin-bottom:1rem;border-radius:4px;}
.ai-ok{background:rgba(0,200,83,0.08);border:1px solid rgba(0,200,83,0.3);
  border-radius:10px;padding:0.65rem 1rem;margin-bottom:0.8rem;font-size:0.82rem;}
.ai-off{background:rgba(100,100,100,0.08);border:1px solid rgba(100,100,100,0.25);
  border-radius:10px;padding:0.65rem 1rem;margin-bottom:0.8rem;font-size:0.82rem;}
</style>
""", unsafe_allow_html=True)

try:
    from db.database import init_db
    init_db()
except Exception:
    pass

SCANNER_OK = False
QUEUE_OK = False
SIZER_OK = False

try:
    from analysis.universe import get_universe, get_price_bounds
    from analysis.strategy_sentiment_scanner import (
        StrategySentimentScanner,
        SCAN_PRESETS,
        ACTION_STRONG_BUY,
        ACTION_INVEST,
        _rank_rows,
    )
    SCANNER_OK = True
except Exception as e:
    st.error(f"Scanner: {e}")

def _universe_count(preset: str) -> int:
    try:
        return len(get_universe(preset))
    except Exception:
        return len(get_universe("all"))

try:
    from trading.approval_queue import ApprovalQueue
    QUEUE_OK = True
except Exception:
    pass

try:
    from trading.position_sizer import PositionSizer
    from trading.risk_manager import RiskManager
    SIZER_OK = True
except Exception:
    pass

for k, v in {
    "ss_session": None,
    "ss_preset": "sp500_full",
    "ss_last_scan_ts": None,
    "approval_queue": None,
    "broker": None,
    "risk_manager": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state["approval_queue"] is None and QUEUE_OK:
    st.session_state["approval_queue"] = ApprovalQueue()
if st.session_state["broker"] is None:
    try:
        from trading.mock_broker import MockBroker
        st.session_state["broker"] = MockBroker()
    except Exception:
        pass
if st.session_state["risk_manager"] is None and SIZER_OK:
    try:
        st.session_state["risk_manager"] = RiskManager()
    except Exception:
        pass

st.title("📊 Strategy Signals + Sentiment")
st.markdown(
    "<p class='sub'>S&amp;P 500 scan loads from saved cache instantly — auto-refreshes every 5 min in the background.</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='disc'>⚠️ NOT FINANCIAL ADVICE. STRONG BUY / INVEST labels are algorithmic — "
    "not broker recommendations. Verify prices before trading.</div>",
    unsafe_allow_html=True,
)

# AI status — dual provider
try:
    from ai.analyst import is_gemini_available, is_openai_available
    _gem = is_gemini_available()
    _oai = is_openai_available()
    if _gem or _oai:
        st.markdown(
            f"<div class='ai-ok'>🤖 <strong>Gemini</strong> — default across app ({'✅' if _gem else '❌'}) · "
            f"<strong>ChatGPT</strong> — per-stock analysis ({'✅' if _oai else '❌'})</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='ai-off'>📊 No AI keys — add Gemini (free scan notes) + OpenAI (chat) to <code>.env</code>.</div>",
            unsafe_allow_html=True,
        )
except Exception:
    pass

with st.expander("🔑 AI setup & token savings", expanded=False):
    st.markdown("""
### AI split

| Layer | Provider |
|-------|----------|
| **Everything default** (scan notes, market summaries, general chat) | **Gemini** |
| **Each stock** (AI Summary, ticker chat, research notes) | **ChatGPT** |

`.env`:
```
AI_PROVIDER=gemini
AI_SCAN_PROVIDER=gemini
AI_STOCK_PROVIDER=openai
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```
    """)

if not SCANNER_OK:
    st.stop()

preset_keys = list(SCAN_PRESETS.keys())
preset_vals = list(SCAN_PRESETS.values())
cur_preset = st.session_state.get("ss_preset", "robinhood")
try:
    universe_count = _universe_count(cur_preset)
except Exception:
    universe_count = _universe_count("robinhood")

c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
with c1:
    sel = st.selectbox(
        "Stock universe",
        preset_keys,
        index=preset_vals.index(cur_preset) if cur_preset in preset_vals else 2,
    )
    st.session_state["ss_preset"] = SCAN_PRESETS[sel]
    universe_count = len(get_universe(st.session_state["ss_preset"]))
with c2:
    scan_all = st.checkbox("Scan all", value=False, help=f"Full universe = {universe_count:,} stocks (can take hours)")
with c3:
    limit = st.number_input(
        "Limit", 50, 12000,
        value=min(DEFAULT_SCAN_LIMIT, universe_count),
        step=50,
        disabled=scan_all,
        help="Default 250 — use 500 for full S&P sweep",
    )
with c4:
    workers = st.slider("Speed", 4, 16, 10)

auto_refresh = st.checkbox(
    "Auto-refresh every 5 minutes (background)",
    value=True,
    help="Server refreshes scan in the background; page shows cached results instantly.",
)
if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=get_ui_poll_seconds() * 1000, key="ss_autorefresh")
    except ImportError:
        pass

refresh_col1, refresh_col2, refresh_col3 = st.columns([2, 1, 2])
with refresh_col1:
    scan_clicked = st.button("🔄 Refresh scan now", type="primary", use_container_width=True)
with refresh_col2:
    refresh_prices = st.button("↻ Prices only", use_container_width=True)

ai_col1, ai_col2 = st.columns([1, 3])
with ai_col1:
    enable_ai_notes = st.checkbox(
        "AI notes (Gemini)",
        value=True,
        help="1 free Gemini call adds notes to top 20 picks — not 1 call per stock",
    )
with ai_col2:
    st.caption(
        "Rankings = algorithmic. **Scan AI notes** = Gemini. "
        "**AI Summary** (per stock) = ChatGPT."
    )

st.caption(
    f"Universe: **{universe_count:,}** symbols · "
    f"**STRONG BUY** rows always sorted to top · Prices: live → market → intraday → daily close"
)
if get_price_bounds(st.session_state["ss_preset"]) != (None, None):
    st.info(
        "💰 **Price-filter mode** — scans US listings and keeps only tickers in the selected "
        "price band. First load may take a few extra minutes vs S&P 500."
    )

if universe_count > 1000 and scan_all:
    st.warning(
        f"Scanning all **{universe_count:,}** stocks may take many hours. "
        f"Use **Limit** 250–500 for daily scans."
    )

run_scan = scan_clicked
actual_limit = None if scan_all else int(limit)

if run_scan:
    progress = st.progress(0, text="Refreshing scan…")

    def _cb(d, t):
        progress.progress(d / max(1, t), text=f"Strategy + sentiment: {d}/{t}")

    try:
        session, last_ts, scan_status = resolve_strategy_scan(
            preset=st.session_state["ss_preset"],
            limit=actual_limit,
            scan_all=scan_all,
            enable_ai_notes=enable_ai_notes,
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
            ai_msg = ""
            if session.ai_notes_count:
                ai_msg = f" · **{session.ai_notes_count}** AI notes ({session.ai_scan_provider})"
            st.success(
                f"Done in {session.elapsed_seconds}s — {session.scanned}/{session.universe_size} ranked · "
                f"**{session.strong_buy_count}** STRONG BUY · **{session.invest_count}** INVEST{ai_msg}"
            )
else:
    try:
        session, last_ts, scan_status = resolve_strategy_scan(
            preset=st.session_state["ss_preset"],
            limit=actual_limit,
            scan_all=scan_all,
            enable_ai_notes=enable_ai_notes,
            workers=workers,
            force=False,
            auto_refresh=auto_refresh,
            progress_callback=None,
        )
    except Exception as ex:
        st.error(str(ex))
        session, last_ts, scan_status = None, None, "missing"

scan_status = st.session_state.get("ss_scan_status", scan_status if session else "missing")
with refresh_col3:
    st.caption(
        format_scan_status(
            st.session_state.get("ss_last_scan_ts"),
            auto_refresh,
            refreshing=(scan_status == "refreshing"),
        )
    )

if session is not None:
    st.session_state["ss_session"] = session
    st.session_state["ss_last_scan_ts"] = last_ts
    st.session_state["ss_scan_status"] = scan_status

if scan_status == "cached":
    st.caption("⚡ Loaded from saved scan — no wait on page refresh.")
elif scan_status == "refreshing":
    st.info("🔄 Updating in background — table shows last saved results until refresh completes.")
elif scan_status == "waiting":
    st.info("⏳ First scan in progress on server — reload in ~30s.")

if session and refresh_prices and session.results:
    with st.spinner("Refreshing live prices for top 100..."):
        n = StrategySentimentScanner(max_workers=4).refresh_prices(session.results, max_rows=100)
    st.success(f"Updated {n} prices from live quotes.")

if session and session.results:
    _rank_rows(session.results)
    strong = [r for r in session.results if r.suggested_action == ACTION_STRONG_BUY]
    invest = [r for r in session.results if r.suggested_action == ACTION_INVEST]
    watch = [r for r in session.results if r.suggested_action == "WATCH"]
    avoid = [r for r in session.results if r.suggested_action == "AVOID"]

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Scanned", session.scanned)
    m2.metric("STRONG BUY", len(strong))
    m3.metric("INVEST", len(invest))
    m4.metric("WATCH", len(watch))
    m5.metric("AVOID", len(avoid))
    m6.metric("#1 Pick", session.results[0].ticker if session.results else "—")

    if strong:
        st.success(
            f"Top pick: **{session.results[0].ticker}** — {session.results[0].suggested_action} "
            f"(composite {session.results[0].composite_score:.0f})"
        )

    f1, f2 = st.columns([1, 3])
    with f1:
        show = st.selectbox(
            "Show",
            ["All (ranked)", "STRONG BUY only", "STRONG BUY + INVEST", "INVEST only", "WATCH only", "Top 50"],
        )
    with f2:
        search = st.text_input("Search ticker", placeholder="e.g. NVDA")

    rows = session.results
    if show == "STRONG BUY only":
        rows = [r for r in rows if r.suggested_action == ACTION_STRONG_BUY]
    elif show == "STRONG BUY + INVEST":
        rows = [r for r in rows if r.suggested_action in (ACTION_STRONG_BUY, ACTION_INVEST)]
    elif show == "INVEST only":
        rows = [r for r in rows if r.suggested_action == ACTION_INVEST]
    elif show == "WATCH only":
        rows = [r for r in rows if r.suggested_action == "WATCH"]
    elif show == "Top 50":
        rows = rows[:50]
    if search.strip():
        q = search.strip().upper()
        rows = [r for r in rows if q in r.ticker]

    table = []
    for r in rows:
        table.append({
            "Rank": r.rank,
            "Ticker": r.ticker,
            "Price": f"${r.price:,.2f}",
            "Price Type": r.price_label,
            "Action": r.suggested_action,
            "Composite": f"{r.composite_score:.0f}",
            "Strategy": r.strategy_signal,
            "Strat Score": f"{r.strategy_score:.0f}",
            "Sentiment": r.sentiment_label,
            "Sent Score": f"{r.sentiment_score:.0f}",
            "Analyst": r.analyst,
            "News": f"{r.news_score:.0f}",
            "Sector": r.sector.replace("_", " "),
            "Why": r.why,
            "AI Note (Gemini)": r.ai_note or "—",
            "Stop": f"${r.stop_loss:,.2f}" if r.stop_loss else "—",
            "Target": f"${r.take_profit:,.2f}" if r.take_profit else "—",
        })

    df = pd.DataFrame(table)

    def _color_action(val):
        if val == ACTION_STRONG_BUY:
            return "background-color: rgba(0,229,255,0.18); color: #00E5FF; font-weight: 800"
        if val == ACTION_INVEST:
            return "background-color: rgba(0,200,83,0.15); color: #00C853; font-weight: 700"
        if val == "AVOID":
            return "background-color: rgba(255,23,68,0.1); color: #FF1744"
        return "background-color: rgba(212,175,55,0.08); color: #D4AF37"

    def _color_analyst(val):
        if val == "STRONG BUY":
            return "background-color: rgba(0,229,255,0.12); color: #00E5FF; font-weight: 700"
        if val == "BUY":
            return "color: #00C853; font-weight: 600"
        if val in ("SELL", "STRONG SELL"):
            return "color: #FF1744"
        return ""

    styled = df.style.map(_color_action, subset=["Action"])
    if "Analyst" in df.columns:
        styled = styled.map(_color_analyst, subset=["Analyst"])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(700, 80 + len(df) * 35),
    )

    st.caption(
        "Price Type: **live** = fast_info/market quote · **delayed** = prior daily close. "
        "Click **Refresh top prices** after scan for latest quotes."
    )

    st.divider()
    st.subheader("💼 Suggested Trade (pick from ranked list)")

    if not QUEUE_OK:
        st.warning("Approval queue unavailable.")
    else:
        pick_pool = strong if strong else (invest if invest else session.results[:20])
        labels = [
            f"#{r.rank} {r.ticker} — {r.suggested_action} · {r.composite_score:.0f} · ${r.price:,.2f}"
            for r in pick_pool
        ]
        idx = st.selectbox("Pick stock to propose", range(len(labels)), format_func=lambda i: labels[i])
        pick = pick_pool[idx]

        col_a, col_b = st.columns(2)
        with col_a:
            side = st.radio("Side", ["buy", "sell"], horizontal=True)
            equity = 10000.0
            broker = st.session_state.get("broker")
            if broker and hasattr(broker, "get_account"):
                try:
                    equity = float(broker.get_account().get("equity", 10000) or 10000)
                except Exception:
                    pass
            if SIZER_OK and pick.price > 0:
                try:
                    sz = PositionSizer().calculate(
                        current_price=pick.price,
                        account_equity=equity,
                        stop_loss_price=pick.stop_loss or pick.price * 0.98,
                    )
                    qty = st.number_input(
                        "Shares", 1, max(1, int(sz.max_allowed_qty)),
                        min(5, int(sz.max_allowed_qty)),
                    )
                except Exception:
                    qty = st.number_input("Shares", 1, 1000, 5)
            else:
                qty = st.number_input("Shares", 1, 1000, 5)

        with col_b:
            st.markdown(f"**Why:** {pick.why}")
            st.caption(
                f"{pick.price_label} · Strategy {pick.strategy_signal} · "
                f"Analyst {pick.analyst} · Composite {pick.composite_score:.0f}"
            )

        ai_col1, ai_col2 = st.columns(2)
        with ai_col1:
            if st.button(f"🤖 AI Summary — {pick.ticker}", use_container_width=True):
                st.session_state["ss_ai_ticker"] = pick.ticker
        with ai_col2:
            if st.button(f"💬 Chat about {pick.ticker}", use_container_width=True):
                st.session_state["chat_focus_ticker"] = pick.ticker
                st.session_state["chat_seed_message"] = (
                    f"Give me an educational overview of {pick.ticker} — "
                    f"strategy signal {pick.strategy_signal}, action {pick.suggested_action}, "
                    f"composite {pick.composite_score:.0f}, analyst {pick.analyst}. "
                    f"What should a day trader watch?"
                )
                st.switch_page("pages/6_💬_Trading_Chat.py")

        if st.session_state.get("ss_ai_ticker") == pick.ticker:
            with st.spinner(f"AI analyzing {pick.ticker}…"):
                try:
                    from analysis.stock_analyzer import StockAnalyzer
                    from analysis.sentiment_analyzer import SentimentAnalyzer
                    from ai.analyst import explain_stock_analysis

                    tech = StockAnalyzer().analyze(pick.ticker)
                    sent = SentimentAnalyzer(max_news=8).analyze(pick.ticker, current_price=pick.price)
                    ai_resp = explain_stock_analysis(tech, sentiment=sent if sent.is_valid else None)
                    st.markdown(ai_resp.full_text)
                except Exception as ex:
                    st.error(str(ex))

        if st.button(f"Propose {side.upper()} {qty} × {pick.ticker}", type="primary"):
            try:
                rm = st.session_state.get("risk_manager")
                risk_dict = {"approved": True, "checks_passed": [], "checks_failed": [], "details": {}}
                if rm:
                    rr = rm.approve_trade(symbol=pick.ticker, qty=float(qty), side=side, price=pick.price)
                    risk_dict = {
                        "approved": rr.approved,
                        "checks_passed": rr.checks_passed,
                        "checks_failed": rr.checks_failed,
                        "details": rr.details,
                    }
                    if not rr.approved:
                        st.error(f"Risk blocked: {rr.rejection_summary}")
                        st.stop()

                q = st.session_state["approval_queue"]
                proposal = q.create_proposal(
                    ticker=pick.ticker,
                    side=side,
                    quantity=float(qty),
                    estimated_price=pick.price,
                    strategy_name="StrategySentiment",
                    signal_reason=pick.why[:300],
                    ai_explanation=(
                        f"{pick.suggested_action} | Composite {pick.composite_score:.0f} | "
                        f"Analyst {pick.analyst} | Sentiment {pick.sentiment_score:.0f}"
                    ),
                    risk_result=risk_dict,
                    broker_mode="mock",
                )
                st.success(f"Proposal #{proposal.id} created — approve in Paper Trading.")
            except Exception as ex:
                st.error(str(ex))

elif st.session_state.get("ss_session") is None:
    st.info(
        f"Scanning **{min(DEFAULT_SCAN_LIMIT, universe_count)}** stocks from "
        f"**{sel}** — first load takes 1–3 minutes on cloud."
    )

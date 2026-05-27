"""
Backtest Page — upgraded
Run historical backtests with fee/slippage modelling and expanded performance metrics.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import date

st.set_page_config(
    page_title="Backtest | AI Trading Assistant",
    page_icon="📈",
    layout="wide",
)

# ── Wall Street Dark Theme CSS ────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
:root{--bg-primary:#0a0a0f;--bg-card:rgba(26,26,46,0.72);--accent-gold:#D4AF37;
    --profit-cyan:#00E5FF;--profit-green:#00C853;--loss-red:#FF1744;
    --text-primary:#E0E0E0;--text-muted:#888;
    --glass-border:rgba(212,175,55,0.12);}
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background-color:#0a0a0f;}
.section-header{font-size:1.1rem;font-weight:700;color:var(--accent-gold);text-transform:uppercase;
    letter-spacing:1.5px;padding-bottom:0.5rem;margin-bottom:1rem;
    border-bottom:1px solid rgba(212,175,55,0.18);}
.metric-card{background:var(--bg-card);backdrop-filter:blur(16px);
    border:1px solid var(--glass-border);border-radius:16px;
    padding:1.2rem 1.4rem;box-shadow:0 8px 32px rgba(0,0,0,0.45);
    position:relative;overflow:hidden;transition:all 0.3s ease;min-height:120px;}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,var(--accent-gold),transparent);}
.metric-card:hover{border-color:rgba(212,175,55,0.35);transform:translateY(-2px);}
.metric-label{font-size:0.72rem;font-weight:700;text-transform:uppercase;
    letter-spacing:1.2px;color:#888;margin-bottom:0.3rem;}
.metric-value{font-size:1.6rem;font-weight:800;color:#fff;line-height:1.1;
    font-family:'JetBrains Mono',monospace;}
.metric-sub{font-size:0.78rem;font-weight:600;margin-top:0.2rem;}
.gold-divider{height:1px;background:linear-gradient(90deg,transparent,#D4AF37,transparent);
    margin:1.5rem 0;border:none;}
.warning-box{background:rgba(255,152,0,0.08);border:2px solid rgba(255,152,0,0.4);
    border-radius:14px;padding:1.2rem 1.5rem;margin:1rem 0;}
.disclaimer-banner{background:linear-gradient(135deg,rgba(255,23,68,0.10),rgba(255,152,0,0.08));
    border:2px solid rgba(255,23,68,0.45);border-radius:14px;
    padding:1.2rem 1.8rem;margin:0.5rem 0 1.5rem;}
.disclaimer-banner p{margin:0;font-size:0.95rem;font-weight:700;color:#FF6B6B;
    line-height:1.7;letter-spacing:0.3px;}
.cost-card::before{background:linear-gradient(90deg,#FF6B6B,transparent);}
</style>
""", unsafe_allow_html=True)

# ── Module imports ────────────────────────────────────────────────────────────
try:
    from db.database import init_db
    init_db()
except Exception:
    pass

BT_OK = False
STRATEGIES_AVAILABLE = ["MA Crossover", "RSI", "VWAP"]

try:
    from trading.backtester import Backtester, BacktestResult, BacktestTrade
    BT_OK = True
except Exception:
    pass

try:
    from trading.strategies import get_strategy, STRATEGY_REGISTRY
    STRATEGIES_AVAILABLE = list(STRATEGY_REGISTRY.keys())
except Exception:
    pass

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='margin-bottom:0.5rem;'>
  <h1 style='margin:0;font-size:2rem;font-weight:900;
      background:linear-gradient(135deg,#D4AF37,#F5E6A3);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
      📈 Strategy Backtester
  </h1>
  <p style='margin:0;color:#888;font-size:0.9rem;'>
      Simulate historical performance of trading strategies with realistic cost modelling
  </p>
</div>
""", unsafe_allow_html=True)

# ── Prominent Disclaimer Banner ──────────────────────────────────────────────
st.markdown("""
<div class='disclaimer-banner'>
  <p>⚠️ SIMULATED RESULTS — Backtests are based on historical data and do NOT
  guarantee future performance. Past results are not indicative of future returns.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

# ── Controls ──────────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>⚙️ Backtest Configuration</div>", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
with c1:
    bt_ticker = st.text_input("Ticker Symbol", value="AAPL").upper().strip()
    bt_strategy = st.selectbox("Strategy", STRATEGIES_AVAILABLE)
with c2:
    bt_start = st.date_input("Start Date", value=date(2023, 1, 1))
    bt_capital = st.number_input("Initial Capital ($)", min_value=1000, value=10000, step=500)
with c3:
    bt_end = st.date_input("End Date", value=date(2024, 12, 31))
    bt_pos_size = st.slider("Position Size (%)", min_value=5, max_value=50, value=10,
                            help="Percentage of capital per trade")
with c4:
    bt_fee = st.number_input(
        "Fee Per Trade ($)",
        min_value=0.0,
        value=1.00,
        step=0.25,
        format="%.2f",
        help="Flat commission per order in USD",
    )
    bt_slippage = st.number_input(
        "Slippage (%)",
        min_value=0.0,
        max_value=5.0,
        value=0.1,
        step=0.05,
        format="%.2f",
        help="Price slippage as a percentage (e.g. 0.1 = 0.1%)",
    )

run_bt = st.button("▶ Run Backtest", use_container_width=True, type="primary")

st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)


# ── Helper: metric card HTML ─────────────────────────────────────────────────
def metric_card(label: str, value: str, sub: str = "", sub_color: str = "#888",
                extra_class: str = "") -> str:
    cls = f"metric-card {extra_class}".strip()
    return (
        f"<div class='{cls}'>"
        f"<div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div>"
        f"<div class='metric-sub' style='color:{sub_color};'>{sub}</div>"
        f"</div>"
    )


# ── Run backtest ──────────────────────────────────────────────────────────────
if run_bt:
    if not bt_ticker:
        st.error("Please enter a ticker symbol.")
        st.stop()
    if bt_start >= bt_end:
        st.error("Start date must be before end date.")
        st.stop()

    with st.spinner(f"Running {bt_strategy} backtest on {bt_ticker}…"):
        result = None
        error_msg = None

        if BT_OK:
            try:
                bt = Backtester()
                result = bt.run(
                    symbol=bt_ticker,
                    start=str(bt_start),
                    end=str(bt_end),
                    strategy_name=bt_strategy,
                    initial_capital=float(bt_capital),
                    position_size_pct=bt_pos_size / 100.0,
                    fee_per_trade=float(bt_fee),
                    slippage_pct=float(bt_slippage) / 100.0,   # convert % → decimal
                )
            except Exception as e:
                error_msg = str(e)

        if result is None:
            # ── Demo fallback when backtester unavailable ─────────────────────
            np.random.seed(42)
            n_days = (bt_end - bt_start).days
            initial = float(bt_capital)
            curve = [initial]
            for _ in range(n_days):
                curve.append(curve[-1] * (1 + np.random.randn() * 0.008))
            dates_list = pd.date_range(bt_start, bt_end).strftime("%Y-%m-%d").tolist()[:len(curve)]

            # Compute demo worst day
            daily_changes = [curve[i] - curve[i - 1] for i in range(1, len(curve))]
            worst_idx = int(np.argmin(daily_changes)) + 1 if daily_changes else 0
            worst_pnl = daily_changes[worst_idx - 1] if daily_changes else 0.0
            worst_date = dates_list[worst_idx] if worst_idx < len(dates_list) else ""

            class _R:
                total_return = curve[-1] - initial
                total_return_pct = (curve[-1] / initial - 1) * 100
                win_rate = 58.3
                max_drawdown = -max(0, (max(curve) - min(curve[curve.index(max(curve)):] or [curve[-1]])))
                max_drawdown_pct = -12.4
                num_trades = 18
                winning_trades = 11
                losing_trades = 7
                avg_profit = 185.0
                avg_loss = -95.0
                avg_pnl = 52.3
                sharpe_ratio = 1.24
                sortino_ratio = 1.58
                calmar_ratio = 0.87
                profit_factor = 2.14
                worst_day_pnl = round(worst_pnl, 2)
                worst_day_date = worst_date
                consecutive_losing_trades = 3
                avg_holding_days = 8.2
                total_fees = 36.00
                total_slippage = 12.45
                equity_curve = curve
                dates = dates_list
                initial_capital = initial
                final_capital = curve[-1]
                trades = []

            result = _R()
            if error_msg:
                st.warning(f"Could not run live backtest ({error_msg}). Showing demo results.")
            else:
                st.info("Showing demo backtest results. Connect API keys for live data.")

    if result:
        # ── ROW 1: Core Performance Metrics ───────────────────────────────────
        st.markdown("<div class='section-header'>📊 Performance Metrics</div>", unsafe_allow_html=True)

        pnl = result.total_return
        pnl_pct = result.total_return_pct
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_sub_color = "#00E5FF" if pnl >= 0 else "#FF1744"

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(metric_card(
                "Total Return",
                f"{pnl_sign}${pnl:,.2f}",
                f"{pnl_sign}{pnl_pct:.2f}%",
                pnl_sub_color,
            ), unsafe_allow_html=True)
        with m2:
            wr = result.win_rate
            st.markdown(metric_card(
                "Win Rate",
                f"{wr:.1f}%",
                f"{result.winning_trades}W / {result.losing_trades}L",
                "#00E5FF" if wr >= 50 else "#FF1744",
            ), unsafe_allow_html=True)
        with m3:
            dd = result.max_drawdown_pct
            st.markdown(metric_card(
                "Max Drawdown",
                f"{dd:.2f}%",
                "Worst peak-to-trough",
                "#FF1744",
            ), unsafe_allow_html=True)
        with m4:
            st.markdown(metric_card(
                "Total Trades",
                str(result.num_trades),
                f"Avg PnL: ${result.avg_pnl:.2f}",
                "#D4AF37",
            ), unsafe_allow_html=True)

        # ── ROW 2: Risk Ratios ────────────────────────────────────────────────
        m5, m6, m7, m8 = st.columns(4)
        with m5:
            sr = result.sharpe_ratio
            st.markdown(metric_card(
                "Sharpe Ratio",
                f"{sr:.2f}",
                "Risk-adjusted return",
                "#00E5FF" if sr >= 1 else "#D4AF37",
            ), unsafe_allow_html=True)
        with m6:
            so = result.sortino_ratio
            st.markdown(metric_card(
                "Sortino Ratio",
                f"{so:.2f}",
                "Downside risk-adjusted",
                "#00E5FF" if so >= 1 else "#D4AF37",
            ), unsafe_allow_html=True)
        with m7:
            cal = result.calmar_ratio
            st.markdown(metric_card(
                "Calmar Ratio",
                f"{cal:.2f}",
                "Return / Max Drawdown",
                "#00E5FF" if cal >= 1 else "#D4AF37",
            ), unsafe_allow_html=True)
        with m8:
            pf = result.profit_factor
            pf_display = f"{pf:.2f}" if pf < 999 else "∞"
            st.markdown(metric_card(
                "Profit Factor",
                pf_display,
                "Gross wins / losses",
                "#00E5FF" if pf >= 1.5 else "#FF1744" if pf < 1 else "#D4AF37",
            ), unsafe_allow_html=True)

        # ── ROW 3: Trade-Level Metrics ────────────────────────────────────────
        m9, m10, m11, m12 = st.columns(4)
        with m9:
            st.markdown(metric_card(
                "Avg Win",
                f"+${result.avg_profit:.2f}",
                "Per winning trade",
                "#00E5FF",
            ), unsafe_allow_html=True)
        with m10:
            st.markdown(metric_card(
                "Avg Loss",
                f"-${abs(result.avg_loss):.2f}",
                "Per losing trade",
                "#FF1744",
            ), unsafe_allow_html=True)
        with m11:
            wd_pnl = result.worst_day_pnl
            wd_date = result.worst_day_date
            st.markdown(metric_card(
                "Worst Day P&L",
                f"${wd_pnl:,.2f}",
                wd_date if wd_date else "N/A",
                "#FF1744",
            ), unsafe_allow_html=True)
        with m12:
            st.markdown(metric_card(
                "Max Consec. Losses",
                str(result.consecutive_losing_trades),
                "Consecutive losing trades",
                "#FF1744" if result.consecutive_losing_trades >= 5 else "#D4AF37",
            ), unsafe_allow_html=True)

        # ── ROW 4: Holding & Cost Metrics ─────────────────────────────────────
        m13, m14, m15, m16 = st.columns(4)
        with m13:
            st.markdown(metric_card(
                "Avg Holding Period",
                f"{result.avg_holding_days:.1f}d",
                "Calendar days per trade",
                "#D4AF37",
            ), unsafe_allow_html=True)
        with m14:
            final = result.final_capital
            st.markdown(metric_card(
                "Final Capital",
                f"${final:,.2f}",
                f"Started: ${result.initial_capital:,.0f}",
                "#D4AF37",
            ), unsafe_allow_html=True)
        with m15:
            st.markdown(metric_card(
                "Total Fees Paid",
                f"${result.total_fees:,.2f}",
                f"${bt_fee:.2f} per trade × {result.num_trades}",
                "#FF1744",
                extra_class="cost-card",
            ), unsafe_allow_html=True)
        with m16:
            st.markdown(metric_card(
                "Total Slippage Cost",
                f"${result.total_slippage:,.2f}",
                f"{bt_slippage:.2f}% of price",
                "#FF1744",
                extra_class="cost-card",
            ), unsafe_allow_html=True)

        st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)

        # ── Equity Curve ──────────────────────────────────────────────────────
        st.markdown("<div class='section-header'>📈 Equity Curve</div>", unsafe_allow_html=True)

        ec = result.equity_curve
        dates_ref = getattr(result, "dates", None) or getattr(result, "dates_list_ref", None)

        if dates_ref and len(dates_ref) >= len(ec):
            x_vals = dates_ref[:len(ec)]
        else:
            x_vals = list(range(len(ec)))

        fig_ec = go.Figure()

        # Portfolio value
        fig_ec.add_trace(go.Scatter(
            x=x_vals, y=ec,
            mode="lines",
            line=dict(color="#D4AF37", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(212,175,55,0.07)",
            name="Portfolio Value",
        ))

        # Initial capital reference line
        fig_ec.add_trace(go.Scatter(
            x=x_vals,
            y=[result.initial_capital] * len(ec),
            mode="lines",
            line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
            name="Initial Capital",
        ))

        fig_ec.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(26,26,46,0.5)",
            height=370,
            margin=dict(l=0, r=0, t=20, b=0),
            yaxis=dict(gridcolor="rgba(255,255,255,0.04)", title="Portfolio Value ($)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_ec, use_container_width=True)

        # ── Trade History Table ───────────────────────────────────────────────
        if hasattr(result, "trades") and result.trades:
            st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
            st.markdown("<div class='section-header'>🗒️ Trade History</div>", unsafe_allow_html=True)

            trade_rows = []
            for t in result.trades:
                pnl_t = getattr(t, "pnl", 0) or 0
                fee_t = getattr(t, "fee", 0) or 0
                slip_t = getattr(t, "slippage", 0) or 0
                hold_t = getattr(t, "holding_days", 0) or 0
                trade_rows.append({
                    "Entry Date": getattr(t, "entry_date", ""),
                    "Exit Date": getattr(t, "exit_date", ""),
                    "Side": getattr(t, "side", "buy").upper(),
                    "Entry Price": f"${getattr(t, 'entry_price', 0):.2f}",
                    "Exit Price": f"${getattr(t, 'exit_price', 0):.2f}",
                    "Qty": f"{getattr(t, 'qty', 0):.0f}",
                    "P&L": f"{'+'if pnl_t>=0 else ''}${pnl_t:.2f}",
                    "Return": f"{getattr(t,'pnl_pct',0)*100:.2f}%",
                    "Fees": f"${fee_t:.2f}",
                    "Slippage": f"${slip_t:.2f}",
                    "Hold (d)": str(hold_t),
                })

            tr_df = pd.DataFrame(trade_rows)

            def color_pnl(val):
                if isinstance(val, str):
                    if "+" in val:
                        return "color:#00E5FF;"
                    if "-" in val and "$" in val:
                        return "color:#FF1744;"
                return ""

            st.dataframe(
                tr_df.style.applymap(color_pnl, subset=["P&L", "Return"]),
                use_container_width=True,
                hide_index=True,
            )

        # ── Analysis Notes ────────────────────────────────────────────────────
        st.markdown("<div class='gold-divider'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='warning-box'>
          <p style='margin:0;font-weight:700;color:#FFA726;'>📝 Backtest Analysis Notes</p>
          <ul style='margin:0.5rem 0 0;color:#ccc;font-size:0.85rem;line-height:1.8;'>
            <li>Fees modelled at <strong>${bt_fee:.2f}</strong> per order (entry + exit)</li>
            <li>Slippage modelled at <strong>{bt_slippage:.2f}%</strong> of fill price</li>
            <li>A Sharpe ratio &gt; 1.0 is generally considered good; &gt; 2.0 is excellent</li>
            <li>Sortino ratio penalises only <strong>downside</strong> volatility — often more relevant than Sharpe</li>
            <li>Profit factor &gt; 1.5 suggests a robust edge; &lt; 1.0 means losses exceed wins</li>
            <li>Max drawdown represents the largest peak-to-trough decline in portfolio value</li>
            <li>Strategy uses end-of-day signals; intraday execution may vary</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)

else:
    # ── Empty state ───────────────────────────────────────────────────────────
    st.markdown("""
    <div style='text-align:center;padding:4rem 2rem;color:#888;'>
      <div style='font-size:4rem;margin-bottom:1rem;'>📊</div>
      <p style='font-size:1.2rem;font-weight:600;color:#D4AF37;'>Ready to Run a Backtest</p>
      <p style='font-size:0.9rem;'>Configure the parameters above and click <strong>Run Backtest</strong>.</p>
      <p style='font-size:0.8rem;margin-top:1rem;'>
        Enter a ticker symbol, choose a strategy, set date range, capital, fees,
        and slippage to see how the strategy would have performed on historical data.
      </p>
    </div>
    """, unsafe_allow_html=True)

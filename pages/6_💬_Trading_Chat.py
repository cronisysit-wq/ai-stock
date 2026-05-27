"""
Trading Chat — ask anything about stocks, strategies, or market concepts.

Uses OpenAI/Gemini with live technical + sentiment context when a ticker is mentioned.

NOT FINANCIAL ADVICE.
"""

import streamlit as st

st.set_page_config(page_title="Trading Chat", page_icon="💬", layout="wide")

st.markdown("""
<style>
html,body,[class*="css"]{font-family:Inter,sans-serif!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
.stApp{background:#0a0a12;}
h1{color:#D4AF37;font-size:1.6rem;}
.disc{background:rgba(255,167,38,0.08);border-left:3px solid #FFA726;padding:0.6rem 0.9rem;
  font-size:0.8rem;color:#FFA726;margin-bottom:1rem;border-radius:4px;}
</style>
""", unsafe_allow_html=True)

try:
    from db.database import init_db
    init_db()
except Exception:
    pass

from ai.trading_chat import ChatMessage, chat
from ai.analyst import get_active_ai_provider, is_ai_available

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_focus_ticker" not in st.session_state:
    st.session_state.chat_focus_ticker = ""

# Seed from Strategy Signals or other pages
if st.session_state.get("chat_seed_message"):
    seed = st.session_state.pop("chat_seed_message")
    st.session_state.chat_history.append(ChatMessage(role="user", content=seed))

st.title("💬 Trading Chat")
st.markdown(
    "Ask about **any stock** (e.g. *Should I watch NVDA?*), **indicators** (*What is RSI?*), "
    "or **day trading rules**. AI pulls live price, technicals, and sentiment when you mention a ticker."
)
st.markdown(
    "<div class='disc'>⚠️ NOT FINANCIAL ADVICE. Chat explains only — it cannot place orders.</div>",
    unsafe_allow_html=True,
)

provider = get_active_ai_provider()
if is_ai_available():
    st.success("🤖 **Gemini** — general chat · **ChatGPT** — when you ask about a specific stock")
else:
    st.warning("📊 No AI key — add `OPENAI_API_KEY` to `.env` for full answers. Rule-based preview only.")

with st.sidebar:
    st.markdown("### Focus ticker")
    focus = st.text_input(
        "Optional symbol",
        value=st.session_state.get("chat_focus_ticker", ""),
        placeholder="e.g. AAPL",
        key="chat_focus_input",
    ).strip().upper()
    st.session_state.chat_focus_ticker = focus
    if focus:
        st.caption(f"Questions will include **{focus}** context even if you don't type the symbol.")

    st.markdown("### Quick prompts")
    prompts = [
        f"What does the data say about {focus or 'AAPL'}?",
        "Explain RSI and MACD for beginners",
        "What is a good day trading risk rule?",
        "How do I read STRONG BUY vs INVEST in Strategy Signals?",
        "What moves the US market on a red day?",
    ]
    for p in prompts:
        if st.button(p, key=f"qp_{p[:20]}", use_container_width=True):
            st.session_state.chat_pending = p
            st.rerun()

    if st.button("Clear chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# Display history
for msg in st.session_state.chat_history:
    with st.chat_message("user" if msg.role == "user" else "assistant"):
        st.markdown(msg.content)

# Handle pending quick prompt or chat input
pending = st.session_state.pop("chat_pending", None)
user_input = pending or st.chat_input("Ask a trading question…")

if user_input:
    st.session_state.chat_history.append(ChatMessage(role="user", content=user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            resp = chat(
                user_input,
                history=st.session_state.chat_history[:-1],
                focus_ticker=focus or None,
            )
        badge = f"*{resp.ai_provider}*" if resp.ai_powered else "*rule-based preview*"
        if resp.tickers_used:
            badge += f" · data: {', '.join(resp.tickers_used)}"
        st.caption(badge)
        st.markdown(resp.full_text)

    st.session_state.chat_history.append(ChatMessage(role="assistant", content=resp.full_text))

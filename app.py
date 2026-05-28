"""
AI Trading Assistant — entry point with clean sidebar navigation.

Sidebar (6 items):
  Trading Modes · Strategy Signals · US Market · Paper Trading · Settings · Logs
"""

import streamlit as st

# Start warming default scan caches once per server process (non-blocking).
if "scan_cache_warmed" not in st.session_state:
    st.session_state["scan_cache_warmed"] = True
    try:
        from ui.scan_service import warm_default_caches
        warm_default_caches()
    except Exception:
        pass

st.set_page_config(
    page_title="AI Trading Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation(
    [
        st.Page("pages/0_🚀_Trading_Modes.py", title="Trading Modes", icon="🚀", default=True),
        st.Page("pages/1_📊_Strategy_Signals.py", title="Strategy Signals", icon="📊"),
        st.Page("pages/2_📡_US_Market.py", title="US Market", icon="📡"),
        st.Page("pages/3_💼_Paper_Trading.py", title="Paper Trading", icon="💼"),
        st.Page("pages/6_💬_Trading_Chat.py", title="Trading Chat", icon="💬"),
        st.Page("pages/4_⚙️_Settings.py", title="Settings", icon="⚙️"),
        st.Page("pages/5_📋_Logs.py", title="Logs", icon="📋"),
    ],
    position="sidebar",
)

pg.run()

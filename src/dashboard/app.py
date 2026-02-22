"""Advuman Streamlit Dashboard — main entry point.

Launch: streamlit run src/dashboard/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Advuman — Trade Lane Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Navigation
pg = st.navigation(
    [
        st.Page("src/dashboard/pages/lane_overview.py", title="Lane Overview", icon="📊", default=True),
        st.Page("src/dashboard/pages/signal_log.py", title="Signal Log", icon="📋"),
        st.Page("src/dashboard/pages/index_charts.py", title="Index Charts", icon="📈"),
    ]
)

pg.run()

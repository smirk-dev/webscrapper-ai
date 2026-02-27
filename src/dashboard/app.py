"""Advuman Streamlit Dashboard — main entry point.

Launch: streamlit run src/dashboard/app.py
"""

import os
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


try:
    secrets = dict(st.secrets)
except StreamlitSecretNotFoundError:
    secrets = {}

if "DATABASE_URL" in secrets and not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = secrets["DATABASE_URL"]

if "ANTHROPIC_API_KEY" in secrets and not os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = secrets["ANTHROPIC_API_KEY"]

if not os.getenv("DATABASE_URL"):
    st.error("DATABASE_URL is not configured. Set it in Streamlit secrets or environment variables.")
    st.stop()

def build_navigation():
    st.set_page_config(
        page_title="Advuman — Trade Lane Intelligence",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    pages_dir = Path(__file__).resolve().parent / "pages"

    return st.navigation(
        [
            st.Page(str(pages_dir / "lane_overview.py"), title="Lane Overview", icon="📊", default=True),
            st.Page(str(pages_dir / "signal_log.py"), title="Signal Log", icon="📋"),
            st.Page(str(pages_dir / "index_charts.py"), title="Index Charts", icon="📈"),
        ]
    )


def main() -> None:
    build_navigation().run()


if __name__ == "__main__":
    main()

import sys
from pathlib import Path

DIMBESS_DIR = str(Path(__file__).resolve().parent.parent)
if DIMBESS_DIR not in sys.path:
    sys.path.insert(0, DIMBESS_DIR)

import streamlit as st

import theme

#----------------------------------------BRANDING----------------------------------------

st.logo(theme.LOGO_FULL_WHITE_PATH, size="small")

st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        background-color: #2E2C67;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF;
    }
    [data-testid="stSidebarNav"] a {
        color: #FFFFFF !important;
        border-radius: 8px;
    }
    [data-testid="stSidebarNav"] a:hover {
        background-color: rgba(255, 255, 255, 0.10);
    }
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background-color: rgba(255, 255, 255, 0.20);
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True
)

#----------------------------------------PAGE SETUP----------------------------------------

home_page = st.Page(
    page="pages/Homepage.py",
    title="Homepage",
    icon="🏠",
    default=True
)

page0 = st.Page(
    page="pages/Scenario_Builder.py",
    title="Scenario Builder",
    icon="🛠️"
)

page1 = st.Page(
    page="pages/Overview.py",
    title="Scenario Overview",
    icon="ℹ️"
)

page2 = st.Page(
    page="pages/Performance.py",
    title="Performance KPIs",
    icon="📊"
)

page3 = st.Page(
    page="pages/Operation.py",
    title="BESS Operation Visualizer",
    icon="📈"
)

page4 = st.Page(
    page="pages/Seasonality.py",
    title="BESS Operation Seasonality",
    icon="📆"
)

#----------------------------------------NAVIGATION SETUP----------------------------------------

pg = st.navigation(pages=[home_page, page0, page1, page2, page3, page4])

#----------------------------------------RUN SETUP----------------------------------------

pg.run()

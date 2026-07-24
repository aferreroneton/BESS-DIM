import sys
from pathlib import Path

DIMBESS_DIR = str(Path(__file__).resolve().parent.parent)
if DIMBESS_DIR not in sys.path:
    sys.path.insert(0, DIMBESS_DIR)

import streamlit as st

#----------------------------------------PAGE SETUP----------------------------------------

home_page = st.Page(
    page="pages/Homepage.py",
    title="Homepage",
    icon="🏠",
    default=True
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

pg = st.navigation(pages=[home_page, page1, page2, page3, page4])

#----------------------------------------RUN SETUP----------------------------------------

pg.run()

import sys
from pathlib import Path

DIMBESS_DIR = str(Path(__file__).resolve().parent.parent)
if DIMBESS_DIR not in sys.path:
    sys.path.insert(0, DIMBESS_DIR)

import streamlit as st

import theme

#----------------------------------------BRANDING----------------------------------------

st.logo(theme.LOGO_FULL_WHITE_PATH, size="large")

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
    /* Los desplegables (ej. selector de escenario) abren un popover con fondo
       claro; la regla de arriba pone el texto en blanco para todo lo que cuelga
       del sidebar, incluido ese popover, dejándolo ilegible (blanco sobre blanco).
       Se restaura el texto oscuro solo dentro del popover/listbox. */
    [data-testid="stSidebar"] [data-baseweb="popover"],
    [data-testid="stSidebar"] [data-baseweb="popover"] * {
        color: #2E2C67 !important;
    }
    /* Páginas tipo Overview/Performance meten muchas st.columns estrechas con números
       y etiquetas largas (ej. "KPI BESS Utilization (Cycles/Day)", "3.792.107,18").
       Por defecto un hijo flex no encoge por debajo del ancho de su contenido
       (min-width:auto), así que en pantallas más estrechas esas columnas empujaban el
       resto fuera de la vista (el pie chart y las columnas de la derecha quedaban
       cortados) en vez de reajustarse. Se fuerza min-width:0 para que sí encojan, y que
       el texto salte de línea en vez de desbordar. */
    [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        min-width: 0 !important;
    }
    [data-testid="stHorizontalBlock"] > div[data-testid="column"] * {
        overflow-wrap: break-word;
        word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True
)

#----------------------------------------PAGE SETUP----------------------------------------

# Iconos ":material/xxx:" (Google Material Symbols, integrados en Streamlit >=1.31):
# son glifos de fuente vectorial, no imágenes, así que heredan el color del texto del
# nav (blanco, ver CSS de arriba) sin tener que descargar ni recolorear nada.
home_page = st.Page(
    page="pages/Homepage.py",
    title="Homepage",
    icon=":material/home:",
    default=True
)

page0 = st.Page(
    page="pages/Scenario_Builder.py",
    title="Scenario Builder",
    icon=":material/build:"
)

page_results = st.Page(
    page="pages/Scenario_Results.py",
    title="Scenario Results",
    icon=":material/fact_check:"
)

page_projection = st.Page(
    page="pages/Savings_Projection.py",
    title="Savings Projection",
    icon=":material/timeline:"
)

page1 = st.Page(
    page="pages/Overview.py",
    title="Scenario Overview",
    icon=":material/dashboard:"
)

page2 = st.Page(
    page="pages/Performance.py",
    title="Performance KPIs",
    icon=":material/monitoring:"
)

page3 = st.Page(
    page="pages/Operation.py",
    title="BESS Operation Visualizer",
    icon=":material/bolt:"
)

page4 = st.Page(
    page="pages/Seasonality.py",
    title="BESS Operation Seasonality",
    icon=":material/calendar_month:"
)

page5 = st.Page(
    page="pages/Contracted_Power.py",
    title="Contracted Power",
    icon=":material/electric_bolt:"
)

#----------------------------------------NAVIGATION SETUP----------------------------------------

pg = st.navigation(pages=[home_page, page0, page_results, page_projection, page1, page2, page3, page4, page5])

#----------------------------------------RUN SETUP----------------------------------------

pg.run()

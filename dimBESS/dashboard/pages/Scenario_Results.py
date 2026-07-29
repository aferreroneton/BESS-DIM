import streamlit as st

import dimBESS
import theme

st.set_page_config(
    page_title="BESS Dashboard - Scenario Results",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Scenario Results")

st.caption(
    "KPIs y proyección de ahorro de todos los escenarios resueltos (desde Homepage o "
    "Scenario Builder): resalta en cyan los que superan el umbral frente al coste de "
    "leasing. Se calcula junto con la resolución del año 1, sin volver a resolver el MILP."
)

kpi_rows = st.session_state.get("kpi_rows", {})

if not kpi_rows:
    st.info("No hay escenarios resueltos todavía. Ve a Homepage y pulsa 'Run Scenarios'.")
    st.stop()

if "kpi_params" in st.session_state:
    hy, th = st.session_state["kpi_params"]
    st.caption(f"Horizonte: {hy} años · Threshold: {th:.0f}% · resaltado = escenario apto")

styled_results = dimBESS.build_results_table(kpi_rows)
raw_columns = styled_results.data.columns

# st.table() rendería el Styler tal cual (formato + resaltado), pero con ~20 columnas
# fuerza el ancho de cada celda y el texto de cabecera se apila letra a letra; con
# st.dataframe() el grid tiene scroll horizontal propio y sí respeta el color de fondo
# del Styler (aunque no su .format(), por eso el formato de € y % se repite aquí vía
# column_config).
column_config = {
    c: st.column_config.NumberColumn(c, format="%.0f €")
    for c in raw_columns if c.startswith("€")
}
column_config["% Savings vs Leasing"] = st.column_config.NumberColumn("% Savings vs Leasing", format="%.1f%%")

st.dataframe(styled_results, column_config=column_config, hide_index=True, width="stretch")

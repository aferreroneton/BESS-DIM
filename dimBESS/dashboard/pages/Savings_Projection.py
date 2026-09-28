import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aux_functions
import dimBESS
import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Savings Projection",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Savings Projection")

results, inputs, scenario, scenario_name = require_scenario()

savings_projections = st.session_state.get("savings_projections", {})
if scenario_name not in savings_projections:
    st.warning(
        "No hay proyección de ahorro calculada para este escenario. Resuélvelo de nuevo "
        "desde Homepage o Scenario Builder (se calcula junto con el resto de KPIs)."
    )
    st.stop()

proyeccion = savings_projections[scenario_name]
study_type = scenario.get("Study Type", "Base study")

st.caption(f"Escenario: **{scenario_name}** · Study Type: **{study_type}**")
st.caption(
    "Savings de BESS (sin mejora PPA) estimados año a año a lo largo de la vida del "
    "proyecto — no acumulados. " + (
        "Basado en el año 1 simulado y la forma empírica real del histórico (58 "
        "simulaciones), con el ajuste de tarifa/container ya calibrado (Base study)."
        if study_type != "Extended study" else
        f"Basado en los años {', '.join(map(str, dimBESS.EXTENDED_STUDY_YEARS))} simulados "
        "(marcados en el gráfico), con la forma entre/más allá de esos puntos calibrada "
        "por el spread real de precios y la degradación de batería (Extended study)."
    )
)

years = proyeccion.index.tolist()
simulated_years = [y for y in (dimBESS.EXTENDED_STUDY_YEARS if study_type == "Extended study" else [1]) if y in years]
marker_sizes = [12 if y in simulated_years else 6 for y in years]

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=years, y=proyeccion.values, mode="lines+markers", showlegend=False,
    line=dict(color=theme.CYAN, width=2),
    marker=dict(size=marker_sizes, color=theme.CYAN, line=dict(width=2, color=theme.CHART_NAVY)),
))

for sim_year in simulated_years:
    fig.add_annotation(
        x=sim_year, y=proyeccion.loc[sim_year],
        text=f"{proyeccion.loc[sim_year]:,.0f} €", showarrow=False, yshift=16,
        font=dict(size=11, color="grey"),
    )

fig.update_layout(
    xaxis_title="Año de operación",
    yaxis_title="€ Savings / año",
    hovermode="x unified",
    margin=dict(t=10, b=10, l=10, r=10),
    height=480,
)
st.markdown(aux_functions.chart_title("Savings BESS estimados por año"), unsafe_allow_html=True)
st.plotly_chart(fig, width="stretch")

download_df = pd.DataFrame({
    "Año de operación": years,
    "€ Savings BESS estimado": proyeccion.values,
    "Simulado": [y in simulated_years for y in years],
})
st.download_button(
    "Descargar datos (CSV)",
    data=download_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
    file_name=f"savings_projection_{scenario_name}.csv",
    mime="text/csv",
    help="Año a año, para comparar directamente contra el histórico/Power BI.",
)

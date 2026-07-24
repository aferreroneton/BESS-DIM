import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Seasonality",
    page_icon=":calendar:",
    layout="wide"
)
st.title("BESS Model")
st.subheader("BESS Operation Seasonality")

results, inputs, scenario, scenario_name = require_scenario()
st.caption(f"Escenario: **{scenario_name}**")

data_base = st.session_state.get("data_base")
if data_base is None:
    st.info("No hay datos horarios base disponibles (vuelve a Homepage).")
    st.stop()

meses = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

month_order = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

n = min(len(data_base), len(results))
data_reset = data_base.reset_index(drop=True).iloc[:n]
results_reset = results.reset_index(drop=True).iloc[:n]

carga = pd.DataFrame()
carga["Mes"] = data_reset["Month num"].map(meses)
carga["Mes"] = pd.Categorical(carga["Mes"], categories=month_order, ordered=True)
carga["Hora"] = data_reset["HourOfDay"]
carga["Periodo"] = data_reset["Period"]
carga["Weekday"] = pd.Categorical(data_reset["Weekday"], categories=weekday_order, ordered=True)
carga["PV"] = results_reset["Carga de PV"]
carga["Red"] = results_reset["Carga de red"]
carga["Total"] = carga["PV"] + carga["Red"]
carga.index = pd.to_datetime(results_reset["Date&Time"])

value_options = ["PV", "Red", "Total"]

value_sel = st.selectbox("Tipo de carga", value_options, index=0)

rows_options = {
    "Mes"               :   "Mes",
    "Hora"              :   "Hora",
    "Periodo"           :   "Periodo",
    "Día de la semana"  :   "Weekday"
}

row_sel = st.selectbox("Filas", list(rows_options.keys()), index=1)

cols_options = [k for k in rows_options.keys() if k != row_sel]

col_sel = st.selectbox("Columnas", cols_options, index=0)


def p10(x): return np.nanpercentile(x, 10)
def p25(x): return np.nanpercentile(x, 25)
def p50(x): return np.nanpercentile(x, 50)
def p75(x): return np.nanpercentile(x, 75)
def p90(x): return np.nanpercentile(x, 90)
def p100(x): return np.nanpercentile(x, 100)


agg_options = {
    "Suma": "sum",
    "Media": "mean",
    "P10": p10,
    "P25": p25,
    "P50": p50,
    "P75": p75,
    "P90": p90,
    "P100": p100
}

agg_sel = st.selectbox("Tipo de agregación", agg_options, index=0)

heatmap_df = carga.pivot_table(
    index=rows_options[row_sel],
    columns=rows_options[col_sel],
    values=value_sel,
    aggfunc=agg_options[agg_sel]
)

if rows_options[row_sel] == "Hora":
    heatmap_df = heatmap_df.sort_index()
if rows_options[col_sel] == "Hora":
    heatmap_df = heatmap_df.sort_index(axis=1)

fig = go.Figure(
    data=go.Heatmap(
        z=heatmap_df.values,
        x=heatmap_df.columns,
        y=heatmap_df.index,
        colorscale=[[0.0, theme.CORAL_LIGHT], [1.0, theme.CORAL_DARK]],
        colorbar=dict(title=value_sel),
        hovertemplate=(
            f"{row_sel}: %{{y}}<br>"
            f"{col_sel}: %{{x}}<br>"
            f"{agg_sel}: %{{z}}<extra></extra>"
        )
    )
)

fig.update_layout(
    title=f"{value_sel} - {agg_sel}",
    xaxis_title=col_sel,
    yaxis_title=row_sel,
    height=500,
    margin=dict(l=80, r=80, t=60, b=60)
)

st.plotly_chart(fig, use_container_width=True)

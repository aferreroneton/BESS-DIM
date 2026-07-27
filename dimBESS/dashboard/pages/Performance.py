import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aux_functions
import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Performance",
    page_icon=theme.LOGO_IMAGE,
    layout="wide"
)
st.title("BESS Model")
st.subheader("Performance KPIs")

results, inputs, scenario, scenario_name = require_scenario()
st.caption(f"Escenario: **{scenario_name}**")

ppa_price = inputs["PPA Price"]

results = results.copy()
results["Date&Time"] = pd.to_datetime(results["Date&Time"])

min_date = results["Date&Time"].min().date()
max_date = results["Date&Time"].max().date()

dates = st.date_input(
    "Selecciona el rango de fechas:",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if isinstance(dates, tuple) and len(dates) == 2:
    start_date, end_date = dates
else:
    start_date, end_date = min_date, max_date

filtered_results = results[(results["Date&Time"].dt.date >= start_date) & (results["Date&Time"].dt.date <= end_date)]

calc_data = aux_functions.calculate_table(filtered_results, ppa_price, inputs)
table_col, chart_col = st.columns([1, 3])

with table_col:

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    kpi_capt_spread = calc_data["KPI Captured Spread"]

    fig_1 = go.Figure(go.Indicator(
        mode="gauge+number",
        value=kpi_capt_spread,
        number={"suffix": "%"},
        title="KPI Captured Spread",
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": theme.NAVY_LIGHT},
            "bgcolor": "white",
        }
    ))

    fig_1.update_layout(height=250, margin={'t': 30, 'b': 0, 'l': 20, 'r': 30})
    st.plotly_chart(fig_1, use_container_width=True)

    r1c1 = st.columns(1)
    r1c1[0].markdown(aux_functions.metric_cell(calc_data["% Charge from PV"], "% Charge from PV", suffix=" %"), unsafe_allow_html=True)

    r2c1 = st.columns(1)
    r2c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh Max Grid Pot. Spread"], "€/MWh Max Grid Pot. Spread"), unsafe_allow_html=True)

    r3c1 = st.columns(1)
    r3c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Captured Spread"], "€/MWh BESS Captured Spread"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    kpi_best_ut = calc_data["KPI BESS Utilization (Cycles/Day)"]

    fig_2 = go.Figure(go.Indicator(
        mode="gauge+number",
        value=kpi_best_ut,
        number={"suffix": "%"},
        title="KPI BESS Utilization (Cycles/Day)",
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": theme.NAVY_LIGHT},
            "bgcolor": "white",
        }
    ))

    fig_2.update_layout(height=250, margin={'t': 30, 'b': 0, 'l': 20, 'r': 30})
    st.plotly_chart(fig_2, use_container_width=True)

    r4c1 = st.columns(1)
    r4c1[0].markdown(aux_functions.metric_cell(calc_data["# BESS Cycles"], "# BESS Cycles"), unsafe_allow_html=True)

    r5c1 = st.columns(1)
    r5c1[0].markdown(aux_functions.metric_cell(calc_data["# Days"], "# Days"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    kpi_charging_opt = calc_data["KPI Charging Optimization"]

    fig_3 = go.Figure(go.Indicator(
        mode="gauge+number",
        value=kpi_charging_opt,
        number={"suffix": "%"},
        title="KPI Charging Optimization",
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": theme.NAVY_LIGHT},
            "bgcolor": "white",
        }
    ))

    fig_3.update_layout(height=250, margin={'t': 30, 'b': 0, 'l': 20, 'r': 30})
    st.plotly_chart(fig_3, use_container_width=True)

    r6c1 = st.columns(1)
    r6c1[0].markdown(aux_functions.metric_cell(calc_data["# Charging hours / Day"], "# Charging hours / Day"), unsafe_allow_html=True)

    r7c1 = st.columns(1)
    r7c1[0].markdown(aux_functions.metric_cell(calc_data["# C/D Hours by C-Factor"], "# C/D Hours by C-Factor"), unsafe_allow_html=True)

with chart_col:

    freq = st.selectbox(
        "Frecuencia",
        options=["Anual", "Trimestral", "Mensual", "Semanal", "Diaria"],
        width=150
    )

    freq_map = {
        "Anual"      : "YS",
        "Trimestral" : "QS",
        "Mensual"    : "MS",
        "Semanal"    : "W",
        "Diaria"     : "D"
    }

    calc_data_freq = aux_functions.freq_kpis(filtered_results, inputs, freq_map[freq])

    fig_4 = go.Figure()

    fig_4.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["€/MWh Max Grid Pot. Spread"],
            name="€/MWh Max Grid Pot. Spread",
            marker_color=theme.NAVY_LIGHT,
            text=[f"{v:.2f}" for v in calc_data_freq["€/MWh Max Grid Pot. Spread"]],
            textposition="outside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_4.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["€/MWh BESS Captured Spread"],
            name="€/MWh BESS Captured Spread",
            marker_color=theme.NAVY_DARK,
            text=[f"{v:.2f}" for v in calc_data_freq["€/MWh BESS Captured Spread"]],
            textposition="outside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_4.add_trace(
        go.Scatter(
            x=calc_data_freq.index,
            y=calc_data_freq["€/MWh AVG Min Price to Charge"],
            name="€/MWh AVG Min Price to Charge",
            mode="lines+markers",
            line=dict(color=theme.ORANGE, width=1)
        )
    )

    fig_4.add_trace(
        go.Scatter(
            x=calc_data_freq.index,
            y=calc_data_freq["€/MWh AVG Max Price to Replace"],
            name="€/MWh AVG Max Price to Replace",
            mode="lines+markers",
            line=dict(color=theme.CYAN, width=1)
        )
    )

    fig_4.update_layout(
        barmode="group",
        height=350,
        legend=dict(orientation="v", x=1.07, y=0.5, xanchor="left", yanchor="top"),
        margin=dict(r=120)
    )

    st.plotly_chart(fig_4, use_container_width=True)

    fig_5 = go.Figure()

    fig_5.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["# Days"],
            name="# Days",
            marker_color=theme.NAVY_LIGHT,
            yaxis="y",
            text=calc_data_freq["# Days"],
            textposition="inside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_5.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["# BESS Cycles"],
            name="# BESS Cycles",
            marker_color=theme.NAVY_DARK,
            yaxis="y",
            text=[f"{v:.2f}" for v in calc_data_freq["# BESS Cycles"]],
            textposition="outside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_5.add_trace(
        go.Scatter(
            x=calc_data_freq.index,
            y=calc_data_freq["KPI BESS Utilization (Cycles/Day)"],
            name="KPI BESS Utilization (Cycles/Day)",
            mode="lines+markers+text",
            line=dict(color=theme.ORANGE, width=1),
            yaxis="y2"
        )
    )

    fig_5.update_layout(
        barmode="group",
        height=350,
        yaxis=dict(),
        yaxis2=dict(overlaying="y", side="right"),
        legend=dict(orientation="v", x=1.07, y=0.5, xanchor="left", yanchor="top"),
        margin=dict(r=140)
    )

    for xi, yi in zip(calc_data_freq.index, calc_data_freq["KPI BESS Utilization (Cycles/Day)"]):
        fig_5.add_annotation(
            x=xi, y=yi, text=f"{yi:.2f}", showarrow=False,
            font=dict(color="black", size=10), bgcolor="rgba(255,255,255,0.7)",
            xanchor="center", yanchor="bottom", yref="y2"
        )

    st.plotly_chart(fig_5, use_container_width=True)

    fig_6 = go.Figure()

    fig_6.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["# Charging hours / Day"],
            name="# Charging hours / Day",
            marker_color=theme.NAVY_LIGHT,
            yaxis="y",
            text=[f"{v:.2f}" for v in calc_data_freq["# Charging hours / Day"]],
            textposition="inside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_6.add_trace(
        go.Bar(
            x=calc_data_freq.index,
            y=calc_data_freq["# C/D Hours by C-Factor"],
            name="# C/D Hours by C-Factor",
            marker_color=theme.NAVY_DARK,
            yaxis="y",
            text=[f"{v:.2f}" for v in calc_data_freq["# C/D Hours by C-Factor"]],
            textposition="outside",
            textfont=dict(color="black", size=10),
        )
    )

    fig_6.add_trace(
        go.Scatter(
            x=calc_data_freq.index,
            y=calc_data_freq["KPI Charging Optimization"],
            name="KPI Charging Optimization",
            mode="lines+markers+text",
            line=dict(color=theme.ORANGE, width=1),
            yaxis="y2"
        )
    )

    fig_6.update_layout(
        barmode="group",
        height=350,
        yaxis=dict(),
        yaxis2=dict(overlaying="y", side="right"),
        legend=dict(orientation="v", x=1.07, y=0.5, xanchor="left", yanchor="top"),
        margin=dict(r=140)
    )

    for xi, yi in zip(calc_data_freq.index, calc_data_freq["KPI Charging Optimization"]):
        fig_6.add_annotation(
            x=xi, y=yi, text=f"{yi:.2f}", showarrow=False,
            font=dict(color="black", size=10), bgcolor="rgba(255,255,255,0.7)",
            xanchor="center", yanchor="bottom", yref="y2"
        )

    st.plotly_chart(fig_6, use_container_width=True)

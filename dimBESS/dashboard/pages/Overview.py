import pandas as pd
import plotly.express as px
import streamlit as st

import aux_functions
import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Overview",
    page_icon=theme.LOGO_IMAGE,
    layout="wide"
)
st.title("BESS Model")
st.subheader("Scenario Overview")

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

ROW_H = 160  # altura de las tarjetas de las filas Energy/Cost/€MWh (3 items)
RESULTS_ROW_H = 260  # altura de las tarjetas de la fila Results (hasta 5 items)


def header(text, bg_color=None):
    style = f"background-color:{bg_color}; padding:8px 10px; border-radius:8px 8px 0 0;" if bg_color else "padding:8px 10px;"
    return f"<div style='{style} text-align:left; font-weight:700;'>{text}</div>"


#----------------------------------------ENERGY MWh----------------------------------------

col_headers = st.columns([0.7, 1, 1, 1, 1, 1])
col_headers[0].markdown("&nbsp;", unsafe_allow_html=True)
col_headers[1].markdown(header("As-Is from Grid", theme.NAVY_TINT), unsafe_allow_html=True)
col_headers[2].markdown(header(">> Phase 1: PV Direct SC", theme.CYAN_TINT), unsafe_allow_html=True)
col_headers[3].markdown(header(">> Phase 2: PV Direct SC + BESS", theme.ORANGE_TINT), unsafe_allow_html=True)
col_headers[4].markdown(header("BESS Operations", theme.CORAL_TINT), unsafe_allow_html=True)
col_headers[5].markdown("&nbsp;", unsafe_allow_html=True)

label_col, as_is_col, phase1_col, phase2_col, bess_col, chart_col = st.columns([0.7, 1, 1, 1, 1, 1])

label_col.markdown("**Energy MWh**")

as_is_col.markdown(
    aux_functions.column_card([(calc_data["MWh Demand"], "MWh Demand")], theme.NAVY_TINT, ROW_H),
    unsafe_allow_html=True
)
phase1_col.markdown(
    aux_functions.column_card([
        (calc_data["MWh Unmet Demand after Direct SC"], "MWh Unmet Demand after Direct SC"),
        (calc_data["MWh PV Direct SC"], "MWh PV Direct SC"),
    ], theme.CYAN_TINT, ROW_H),
    unsafe_allow_html=True
)
phase2_col.markdown(
    aux_functions.column_card([
        (calc_data["MWh Unmet Demand after BESS"], "MWh Unmet Demand after BESS"),
        (calc_data["MWh PV Direct SC"], "MWh PV Direct SC"),
        (calc_data["MWh BESS Discharge"], "MWh BESS Discharge"),
    ], theme.ORANGE_TINT, ROW_H),
    unsafe_allow_html=True
)
bess_col.markdown(
    aux_functions.column_card([
        (calc_data["MWh Charge from PV"], "MWh Charge from PV"),
        (calc_data["MWh Charge from Grid"], "MWh Charge from Grid"),
        (calc_data["% Charge from PV"], "% Charge from PV", 2, " %"),
    ], theme.CORAL_TINT, ROW_H),
    unsafe_allow_html=True
)

with chart_col:
    fig = px.pie(
        names=["Grid", "PV"],
        values=[calc_data["MWh Charge from Grid"], calc_data["MWh Charge from PV"]],
        hole=0.6
    )
    fig.update_traces(marker=dict(colors=[theme.CHART_NAVY, theme.CYAN]))
    fig.update_layout(
        title=dict(text="Charging Source Mix (%)", x=0.5, xanchor='center', yanchor='top', font=dict(color='grey', size=12)),
        legend=dict(orientation="h", y=-0.2, x=0.5, xanchor='center', font=dict(size=10)),
        height=ROW_H + 30,
        margin=dict(t=30, b=30, l=0, r=0),
        paper_bgcolor=theme.CORAL_TINT,
        plot_bgcolor=theme.CORAL_TINT
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

#----------------------------------------COST €----------------------------------------

label_col, as_is_col, phase1_col, phase2_col, bess_col, spread_col = st.columns([0.7, 1, 1, 1, 1, 1])

label_col.markdown("**Cost €**")

as_is_col.markdown(
    aux_functions.column_card([(calc_data["€ Cost As-Is"], "€ Cost As-Is")], theme.NAVY_TINT, ROW_H),
    unsafe_allow_html=True
)
phase1_col.markdown(
    aux_functions.column_card([
        (calc_data["€ Cost Grid Phase 1"], "€ Cost Grid Phase 1"),
        (calc_data["€ Cost PV Direct SC"], "€ Cost PV Direct SC"),
    ], theme.CYAN_TINT, ROW_H),
    unsafe_allow_html=True
)
phase2_col.markdown(
    aux_functions.column_card([
        (calc_data["€ Cost Grid Phase 2"], "€ Cost Grid Phase 2"),
        (calc_data["€ Cost PV Direct SC"], "€ Cost PV Direct SC"),
        (calc_data["€ Cost charging"], "€ Cost charging"),
    ], theme.ORANGE_TINT, ROW_H),
    unsafe_allow_html=True
)
bess_col.markdown(
    aux_functions.column_card([
        (calc_data["€ Cost charging from PV"], "€ Cost charging from PV"),
        (calc_data["€ Cost charging from Grid"], "€ Cost charging from Grid"),
        (calc_data["€ BESS Replaced Cost"], "€ BESS Replaced Cost"),
    ], theme.CORAL_TINT, ROW_H),
    unsafe_allow_html=True
)

with spread_col:
    st.markdown(header("Spread", theme.CORAL_TINT), unsafe_allow_html=True)
    st.markdown(
        aux_functions.column_card([
            (calc_data["€/MWh BESS Replaced Price"], "€/MWh BESS Replaced Price"),
            (calc_data["€/MWh BESS Discharge"], "€/MWh BESS Discharge"),
            (calc_data["€/MWh BESS Captured Spread"], "€/MWh BESS Captured Spread"),
        ], theme.CORAL_TINT, ROW_H),
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

#----------------------------------------€/MWh----------------------------------------

label_col, as_is_col, phase1_col, phase2_col, bess_col, kpi_col = st.columns([0.7, 1, 1, 1, 1, 1])

label_col.markdown("**€/MWh**")

as_is_col.markdown(
    aux_functions.column_card([(calc_data["€/MWh As-Is"], "€/MWh As-Is")], theme.NAVY_TINT, ROW_H),
    unsafe_allow_html=True
)
phase1_col.markdown(
    aux_functions.column_card([
        (calc_data["€/MWh Phase 1 Grid"], "€/MWh Phase 1 Grid"),
        (calc_data["€/MWh PV Direct SC"], "€/MWh PV Direct SC"),
    ], theme.CYAN_TINT, ROW_H),
    unsafe_allow_html=True
)
phase2_col.markdown(
    aux_functions.column_card([
        (calc_data["€/MWh Phase 2 Grid"], "€/MWh Phase 2 Grid"),
        (calc_data["€/MWh PV Direct SC"], "€/MWh PV Direct SC"),
        (calc_data["€/MWh BESS Discharge"], "€/MWh BESS Discharge"),
    ], theme.ORANGE_TINT, ROW_H),
    unsafe_allow_html=True
)
bess_col.markdown(
    aux_functions.column_card([
        (calc_data["€/MWh Charge from PV"], "€/MWh Charge from PV"),
        (calc_data["€/MWh Charge from Grid"], "€/MWh Charge from Grid"),
        (calc_data["€/MWh Charge Blended"], "€/MWh Charge Blended"),
    ], theme.CORAL_TINT, ROW_H),
    unsafe_allow_html=True
)

with kpi_col:
    st.markdown(header("Performance KPIs", theme.CORAL_TINT), unsafe_allow_html=True)
    st.markdown(
        aux_functions.column_card([
            (calc_data["KPI Captured Spread"], "KPI Captured Spread", 2, " %"),
            (calc_data["KPI BESS Utilization (Cycles/Day)"], "KPI BESS Utilization (Cycles/Day)", 2, " %"),
            (calc_data["KPI Charging Optimization"], "KPI Charging Optimization", 2, " %"),
        ], theme.CORAL_TINT, ROW_H),
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

#----------------------------------------RESULTS----------------------------------------

label_col, as_is_col, phase1_col, phase2_col, bess_col, chart_col_2 = st.columns([0.7, 1, 1, 1, 1, 1])

label_col.markdown(header("Results", theme.ORANGE_TINT), unsafe_allow_html=True)

as_is_col.markdown(
    aux_functions.column_card([
        (calc_data["€ Cost As-Is"], "€ Cost As-Is"),
        (calc_data["€/MWh As-Is"], "€/MWh As-Is"),
    ]),
    unsafe_allow_html=True
)
phase1_col.markdown(
    aux_functions.column_card([
        (calc_data["% Cover Phase 1"], "% Cover Phase 1", 2, " %"),
        (calc_data["% Direct PV Self-consumption"], "% Direct PV Self-consumption", 2, " %"),
        (calc_data["€ Total Cost Phase 1"], "€ Total Cost Phase 1"),
        (calc_data["€/MWh Total Cost Phase 1"], "€/MWh Total Cost Phase 1"),
        (calc_data["€ Total Savings Phase 1"], "€ Total Savings Phase 1"),
    ], theme.ORANGE_TINT, RESULTS_ROW_H),
    unsafe_allow_html=True
)
phase2_col.markdown(
    aux_functions.column_card([
        (calc_data["% Cover Phase 2"], "% Cover Phase 2", 2, " %"),
        (calc_data["% Total PV Self-consumption"], "% Total PV Self-consumption", 2, " %"),
        (calc_data["€ Total Cost Phase 2"], "€ Total Cost Phase 2"),
        (calc_data["€/MWh Total Cost Phase 2"], "€/MWh Total Cost Phase 2"),
        (calc_data["€ Total Savings Phase 2"], "€ Total Savings Phase 2"),
    ], theme.ORANGE_TINT, RESULTS_ROW_H),
    unsafe_allow_html=True
)
bess_col.markdown(
    aux_functions.column_card([
        (calc_data["% BESS Demand cover"], "% BESS Demand cover", 2, " %"),
        (calc_data["% BESS PV Self-consumption"], "% BESS PV Self-consumption", 2, " %"),
        (calc_data["€ Savings from BESS"], "€ Savings from BESS"),
    ], theme.CORAL_TINT, RESULTS_ROW_H),
    unsafe_allow_html=True
)

with chart_col_2:
    fig_2 = px.pie(
        names=["Grid", "PV", "BESS Discharge"],
        values=[calc_data["MWh Unmet Demand after BESS"], calc_data["MWh PV Direct SC"], calc_data["MWh BESS Discharge"]],
        hole=0.6
    )
    fig_2.update_traces(marker=dict(colors=[theme.CHART_NAVY, theme.CYAN, theme.CORAL_DARK]), showlegend=True)
    fig_2.update_layout(
        title=dict(text="Demand Cover by Source (%)", x=0.5, xanchor='center', font=dict(color='grey', size=12)),
        legend=dict(orientation="h", y=0, x=0.5, xanchor='center', yanchor='top', font=dict(size=10)),
        height=RESULTS_ROW_H + 30,
        margin=dict(t=30, b=30, l=0, r=0),
        paper_bgcolor=theme.CORAL_TINT,
        plot_bgcolor=theme.CORAL_TINT
    )
    st.plotly_chart(fig_2, use_container_width=True, key="charging_source_mix_final")

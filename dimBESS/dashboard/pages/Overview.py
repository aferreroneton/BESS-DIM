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
table_col, chart_col = st.columns([5, 1])

with table_col:

    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
    col1.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
    col2.markdown(f"<div style='background-color:{theme.NAVY_TINT}; text-align:left; font-weight:bold;'>As-Is from Grid</div>", unsafe_allow_html=True)
    col3.markdown(f"<div style='background-color:{theme.CYAN_TINT}; text-align:left; font-weight:bold;'>> Phase 1: PV Direct SC</div>", unsafe_allow_html=True)
    col4.markdown(f"<div style='background-color:{theme.ORANGE_TINT}; text-align:left; font-weight:bold;'>> Phase 2: PV Direct SC + BESS</div>", unsafe_allow_html=True)
    col5.markdown(f"<div style='background-color:{theme.CORAL_TINT}; text-align:left; font-weight:bold;'>BESS Operations</div>", unsafe_allow_html=True)

    r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
    r1c1.markdown("Energy MWh")
    r1c2.markdown(aux_functions.metric_cell(calc_data["MWh Demand"], "MWh Demand"), unsafe_allow_html=True)
    r1c3.markdown(aux_functions.metric_cell(calc_data["MWh Unmet Demand after Direct SC"], "MWh Unmet Demand after Direct SC"), unsafe_allow_html=True)
    r1c4.markdown(aux_functions.metric_cell(calc_data["MWh Unmet Demand after BESS"], "MWh Unmet Demand after BESS"), unsafe_allow_html=True)
    r1c5.markdown(aux_functions.metric_cell(calc_data["MWh Charge from PV"], "MWh Charge from PV", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

    r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
    r2c1.markdown("")
    r2c2.markdown("")
    r2c3.markdown(aux_functions.metric_cell(calc_data["MWh PV Direct SC"], "MWh PV Direct SC"), unsafe_allow_html=True)
    r2c4.markdown(aux_functions.metric_cell(calc_data["MWh PV Direct SC"], "MWh PV Direct SC"), unsafe_allow_html=True)
    r2c5.markdown(aux_functions.metric_cell(calc_data["MWh Charge from Grid"], "MWh Charge from Grid", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

    r3c1, r3c2, r3c3, r3c4, r3c5 = st.columns(5)
    r3c1.markdown("")
    r3c2.markdown("")
    r3c3.markdown("")
    r3c4.markdown(aux_functions.metric_cell(calc_data["MWh BESS Discharge"], "MWh BESS Discharge"), unsafe_allow_html=True)
    r3c5.markdown(aux_functions.metric_cell(calc_data["% Charge from PV"], "% Charge from PV", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

with chart_col:
    fig = px.pie(
        names=["Grid", "PV"],
        values=[
            calc_data["MWh Charge from Grid"],
            calc_data["MWh Charge from PV"]
        ],
        hole=0.6
    )

    fig.update_traces(marker=dict(colors=[theme.CHART_NAVY, theme.CYAN]))

    fig.update_layout(
        title=dict(
            text="Charging Source Mix (%)",
            x=0.5,
            xanchor='center',
            yanchor='top',
            font=dict(color='grey', size=14)
        ),
        legend=dict(
            orientation="h",
            y=-0.2,
            x=0.5,
            xanchor='center',
            font=dict(size=10)
        ),
        height=165,
        margin=dict(t=40, b=40, l=0, r=0),
        paper_bgcolor=theme.CORAL_TINT,
        plot_bgcolor=theme.CORAL_TINT
    )

    st.plotly_chart(fig, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

col1_2, col2_2, col3_2, col4_2, col5_2, col6_2 = st.columns([1, 1, 1, 1, 1, 1])
col1_2.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col2_2.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col3_2.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col4_2.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col5_2.markdown(f"<div style='background-color:{theme.CORAL_TINT}; text-align:left; font-weight:bold;> </div>", unsafe_allow_html=True)
col6_2.markdown(f"<div style='background-color:{theme.CORAL_TINT}; text-align:left; font-weight:bold;'>Spread</div>", unsafe_allow_html=True)

r4c1, r4c2, r4c3, r4c4, r4c5, r4c6 = st.columns(6)
r4c1.markdown("Cost €")
r4c2.markdown(aux_functions.metric_cell(calc_data["€ Cost As-Is"], "€ Cost As-Is"), unsafe_allow_html=True)
r4c3.markdown(aux_functions.metric_cell(calc_data["€ Cost Grid Phase 1"], "€ Cost Grid Phase 1"), unsafe_allow_html=True)
r4c4.markdown(aux_functions.metric_cell(calc_data["€ Cost Grid Phase 2"], "€ Cost Grid Phase 2"), unsafe_allow_html=True)
r4c5.markdown(aux_functions.metric_cell(calc_data["€ Cost charging from PV"], "€ Cost charging from PV", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r4c6.markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Replaced Price"], "€/MWh BESS Replaced Price", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

r5c1, r5c2, r5c3, r5c4, r5c5, r5c6 = st.columns(6)
r5c1.markdown("")
r5c2.markdown("")
r5c3.markdown(aux_functions.metric_cell(calc_data["€ Cost PV Direct SC"], "€ Cost PV Direct SC"), unsafe_allow_html=True)
r5c4.markdown(aux_functions.metric_cell(calc_data["€ Cost PV Direct SC"], "€ Cost PV Direct SC"), unsafe_allow_html=True)
r5c5.markdown(aux_functions.metric_cell(calc_data["€ Cost charging from Grid"], "€ Cost charging from Grid", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r5c6.markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Discharge"], "€/MWh BESS Discharge", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

r6c1, r6c2, r6c3, r6c4, r6c5, r6c6 = st.columns(6)
r6c1.markdown("")
r6c2.markdown("")
r6c3.markdown("")
r6c4.markdown(aux_functions.metric_cell(calc_data["€ Cost charging"], "€ Cost charging"), unsafe_allow_html=True)
r6c5.markdown(aux_functions.metric_cell(calc_data["€ BESS Replaced Cost"], "€ BESS Replaced Cost", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r6c6.markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Captured Spread"], "€/MWh BESS Captured Spread", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

col1_3, col2_3, col3_3, col4_3, col5_3, col6_3 = st.columns([1, 1, 1, 1, 1, 1])
col1_3.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col2_3.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col3_3.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col4_3.markdown("<div style='text-align:left; font-weight:bold;'> </div>", unsafe_allow_html=True)
col5_3.markdown(f"<div style='background-color:{theme.CORAL_TINT}; text-align:left; font-weight:bold;> </div>", unsafe_allow_html=True)
col6_3.markdown(f"<div style='background-color:{theme.CORAL_TINT}; text-align:left; font-weight:bold;'>Performance KPIs</div>", unsafe_allow_html=True)

r7c1, r7c2, r7c3, r7c4, r7c5, r7c6 = st.columns(6)
r7c1.markdown("€/MWh")
r7c2.markdown(aux_functions.metric_cell(calc_data["€/MWh As-Is"], "€/MWh As-Is"), unsafe_allow_html=True)
r7c3.markdown(aux_functions.metric_cell(calc_data["€/MWh Phase 1 Grid"], "€/MWh Phase 1 Grid"), unsafe_allow_html=True)
r7c4.markdown(aux_functions.metric_cell(calc_data["€/MWh Phase 2 Grid"], "€/MWh Phase 2 Grid"), unsafe_allow_html=True)
r7c5.markdown(aux_functions.metric_cell(calc_data["€/MWh Charge from PV"], "€/MWh Charge from PV", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r7c6.markdown(aux_functions.metric_cell(calc_data["KPI Captured Spread"], "KPI Captured Spread", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

r8c1, r8c2, r8c3, r8c4, r8c5, r8c6 = st.columns(6)
r8c1.markdown("")
r8c2.markdown("")
r8c3.markdown(aux_functions.metric_cell(calc_data["€/MWh PV Direct SC"], "€/MWh PV Direct SC"), unsafe_allow_html=True)
r8c4.markdown(aux_functions.metric_cell(calc_data["€/MWh PV Direct SC"], "€/MWh PV Direct SC"), unsafe_allow_html=True)
r8c5.markdown(aux_functions.metric_cell(calc_data["€/MWh Charge from Grid"], "€/MWh Charge from Grid", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r8c6.markdown(aux_functions.metric_cell(calc_data["KPI BESS Utilization (Cycles/Day)"], "KPI BESS Utilization (Cycles/Day)", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

r9c1, r9c2, r9c3, r9c4, r9c5, r9c6 = st.columns(6)
r9c1.markdown("")
r9c2.markdown("")
r9c3.markdown("")
r9c4.markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Discharge"], "€/MWh BESS Discharge"), unsafe_allow_html=True)
r9c5.markdown(aux_functions.metric_cell(calc_data["€/MWh Charge Blended"], "€/MWh Charge Blended", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)
r9c6.markdown(aux_functions.metric_cell(calc_data["KPI Charging Optimization"], "KPI Charging Optimization", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

table_col_2, chart_col_2 = st.columns([5, 1])

with table_col_2:

    r10c1, r10c2, r10c3, r10c4, r10c5 = st.columns(5)
    r10c1.markdown(f"<div style='background-color:{theme.ORANGE_TINT}; text-align:left; font-weight:bold;'>Results</div>", unsafe_allow_html=True)
    r10c2.markdown("")
    r10c3.markdown(aux_functions.metric_cell(calc_data["% Cover Phase 1"], "% Cover Phase 1", suffix=" %", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r10c4.markdown(aux_functions.metric_cell(calc_data["% Cover Phase 2"], "% Cover Phase 2", suffix=" %", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r10c5.markdown(aux_functions.metric_cell(calc_data["% BESS Demand cover"], "% BESS Demand cover", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

    r11c1, r11c2, r11c3, r11c4, r11c5 = st.columns(5)
    r11c1.markdown("")
    r11c2.markdown("")
    r11c3.markdown(aux_functions.metric_cell(calc_data["% Direct PV Self-consumption"], "% Direct PV Self-consumption", suffix=" %", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r11c4.markdown(aux_functions.metric_cell(calc_data["% Total PV Self-consumption"], "% Total PV Self-consumption", suffix=" %", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r11c5.markdown(aux_functions.metric_cell(calc_data["% BESS PV Self-consumption"], "% BESS PV Self-consumption", suffix=" %", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

    r12c1, r12c2, r12c3, r12c4, r12c5 = st.columns(5)
    r12c1.markdown("")
    r12c2.markdown(aux_functions.metric_cell(calc_data["€ Cost As-Is"], "€ Cost As-Is", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r12c3.markdown(aux_functions.metric_cell(calc_data["€ Total Cost Phase 1"], "€ Total Cost Phase 1", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r12c4.markdown(aux_functions.metric_cell(calc_data["€ Total Cost Phase 2"], "€ Total Cost Phase 2", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r12c5.markdown("")

    r13c1, r13c2, r13c3, r13c4, r13c5 = st.columns(5)
    r13c1.markdown("")
    r13c2.markdown(aux_functions.metric_cell(calc_data["€/MWh As-Is"], "€/MWh As-Is", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r13c3.markdown(aux_functions.metric_cell(calc_data["€/MWh Total Cost Phase 1"], "€/MWh Total Cost Phase 1", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r13c4.markdown(aux_functions.metric_cell(calc_data["€/MWh Total Cost Phase 2"], "€/MWh Total Cost Phase 2", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r13c5.markdown("")

    r14c1, r14c2, r14c3, r14c4, r14c5 = st.columns(5)
    r14c1.markdown("")
    r14c2.markdown("")
    r14c3.markdown(aux_functions.metric_cell(calc_data["€ Total Savings Phase 1"], "€ Total Savings Phase 1", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r14c4.markdown(aux_functions.metric_cell(calc_data["€ Total Savings Phase 2"], "€ Total Savings Phase 2", bg_color=theme.ORANGE_TINT), unsafe_allow_html=True)
    r14c5.markdown(aux_functions.metric_cell(calc_data["€ Savings from BESS"], "€ Savings from BESS", bg_color=theme.CORAL_TINT), unsafe_allow_html=True)

with chart_col_2:
    fig_2 = px.pie(
        names=["Grid", "PV", "BESS Discharge"],
        values=[calc_data["MWh Unmet Demand after BESS"], calc_data["MWh PV Direct SC"], calc_data["MWh BESS Discharge"]],
        hole=0.6
    )

    fig_2.update_traces(marker=dict(colors=[theme.CHART_NAVY, theme.CYAN, theme.CORAL_DARK]), showlegend=True)
    fig_2.update_layout(
        title=dict(text="Demand Cover by Source (%)", x=0.5, xanchor='center', font=dict(color='grey', size=14)),
        legend=dict(orientation="h", y=0, x=0.5, xanchor='center', yanchor='top', font=dict(size=10)),
        height=235,
        margin=dict(t=30, b=30, l=0, r=0),
        paper_bgcolor=theme.CORAL_TINT,
        plot_bgcolor=theme.CORAL_TINT
    )

    st.plotly_chart(fig_2, use_container_width=True, key="charging_source_mix_final")

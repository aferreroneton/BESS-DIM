import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aux_functions
import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Operation",
    page_icon=theme.LOGO_IMAGE,
    layout="wide"
)
st.title("BESS Model")
st.subheader("BESS Operation Visualizer")

results, inputs, scenario, scenario_name = require_scenario()
st.caption(f"Escenario: **{scenario_name}**")

data_base = st.session_state.get("data_base")

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
table_col, chart_col = st.columns([1, 6])

with table_col:

    r1c1 = st.columns(1)
    r1c1[0].markdown(aux_functions.metric_cell(calc_data["MWh Charge from PV"], "MWh Charge from PV"), unsafe_allow_html=True)

    r2c1 = st.columns(1)
    r2c1[0].markdown(aux_functions.metric_cell(calc_data["MWh Charge from Grid"], "MWh Charge from Grid"), unsafe_allow_html=True)

    r3c1 = st.columns(1)
    r3c1[0].markdown(aux_functions.metric_cell(calc_data["% Charge from PV"], "% Charge from PV", suffix=" %"), unsafe_allow_html=True)

    r4c1 = st.columns(1)
    r4c1[0].markdown(aux_functions.metric_cell(calc_data["# Charging hours"], "# Charging hours"), unsafe_allow_html=True)

    r5c1 = st.columns(1)
    r5c1[0].markdown(aux_functions.metric_cell(calc_data["# Days"], "# Days"), unsafe_allow_html=True)

    r6c1 = st.columns(1)
    r6c1[0].markdown(aux_functions.metric_cell(calc_data["# Charging hours / Day"], "# Charging hours / Day"), unsafe_allow_html=True)

    r7c1 = st.columns(1)
    r7c1[0].markdown(aux_functions.metric_cell(calc_data["# C/D Hours by C-Factor"], "# C/D Hours by C-Factor"), unsafe_allow_html=True)

    r8c1 = st.columns(1)
    r8c1[0].markdown(aux_functions.metric_cell(calc_data["KPI Charging Optimization"], "KPI Charging Optimization", suffix=" %"), unsafe_allow_html=True)

    r9c1 = st.columns(1)
    r9c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Replaced Price"], "€/MWh BESS Replaced Price"), unsafe_allow_html=True)

    r10c1 = st.columns(1)
    r10c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Discharge"], "€/MWh BESS Discharge"), unsafe_allow_html=True)

    r11c1 = st.columns(1)
    r11c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh BESS Captured Spread"], "€/MWh BESS Captured Spread"), unsafe_allow_html=True)

    r12c1 = st.columns(1)
    r12c1[0].markdown(aux_functions.metric_cell(calc_data["€/MWh Max Grid Pot. Spread"], "€/MWh Max Grid Pot. Spread"), unsafe_allow_html=True)

    r13c1 = st.columns(1)
    r13c1[0].markdown(aux_functions.metric_cell(calc_data["KPI Captured Spread"], "KPI Captured Spread", suffix=" %"), unsafe_allow_html=True)

    r14c1 = st.columns(1)
    r14c1[0].markdown(aux_functions.metric_cell(calc_data["# BESS Cycles"], "# BESS Cycles"), unsafe_allow_html=True)

    r15c1 = st.columns(1)
    r15c1[0].markdown(aux_functions.metric_cell(calc_data["# Days"], "# Days"), unsafe_allow_html=True)

    r16c1 = st.columns(1)
    r16c1[0].markdown(aux_functions.metric_cell(calc_data["KPI BESS Utilization (Cycles/Day)"], "KPI BESS Utilization (Cycles/Day)", suffix=" %"), unsafe_allow_html=True)

    r17c1 = st.columns(1)
    r17c1[0].markdown(aux_functions.metric_cell(calc_data["€ Savings from BESS"], "€ Savings from BESS"), unsafe_allow_html=True)

with chart_col:

    data_plot = pd.DataFrame(index=filtered_results.index)
    data_plot["Date&Time"] = pd.to_datetime(filtered_results["Date&Time"])
    data_plot["MWh PV Direct SC"] = np.where(filtered_results["Producción PV"] > filtered_results["Demanda"], filtered_results["Demanda"], filtered_results["Producción PV"])
    data_plot["MWh Charge from PV"] = filtered_results["Carga de PV"]
    data_plot["MWh BESS Discharge"] = filtered_results["Descarga"]
    data_plot["MWh Unmet Demand after BESS"] = filtered_results["Cobertura red"]
    data_plot["MWh Unstored Surplus"] = np.where(filtered_results["Producción PV"] > (filtered_results["Demanda"] + filtered_results["Carga de PV"]), filtered_results["Producción PV"] - (filtered_results["Demanda"] + filtered_results["Carga de PV"]), 0)
    data_plot["MWh Charge from Grid"] = filtered_results["Carga de red"]
    data_plot["Grid Charging Price"] = filtered_results["Precio Carga Red"]
    data_plot["PV Charging Price"] = filtered_results["Precio Carga PV"]

    mwh_cols = [c for c in data_plot.columns if "MWh" in c]
    price_cols = [c for c in data_plot.columns if "Price" in c]
    colors = {
        "MWh PV Direct SC"              :   theme.ORANGE,
        "MWh Charge from PV"            :   theme.CORAL_DARK,
        "MWh BESS Discharge"            :   theme.CYAN,
        "MWh Unmet Demand after BESS"   :   "#E6E6E6",
        "MWh Unstored Surplus"          :   theme.MUTED,
        "MWh Charge from Grid"          :   theme.CHART_NAVY,
        "Grid Charging Price"           :   theme.CHART_NAVY_LIGHT,
        "PV Charging Price"             :   theme.CORAL_LIGHT
    }

    fig_1 = go.Figure()

    for col in mwh_cols:
        fig_1.add_trace(
            go.Bar(x=data_plot["Date&Time"], y=data_plot[col], name=col, marker_color=colors.get(col), yaxis="y1")
        )

    for col in price_cols:
        fig_1.add_trace(
            go.Scatter(x=data_plot["Date&Time"], y=data_plot[col], name=col, mode="lines", line=dict(color=colors.get(col), width=1), yaxis="y2")
        )

    fig_1.update_layout(
        barmode="stack",
        height=300,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        margin=dict(t=40, b=40, l=50, r=50),
        xaxis=dict(tickformat="%d-%m"),
        yaxis=dict(title="Energy (MWh)", showgrid=True),
        yaxis2=dict(title="Price (€/MWh)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center", itemsizing="constant", itemwidth=35, font=dict(size=10))
    )

    st.plotly_chart(fig_1, use_container_width=True, key="energy_price_mix")

    if data_base is None:
        st.info("No hay datos horarios base disponibles para las agregaciones por periodo/hora (vuelve a Homepage).")
    else:
        col1, col2, col3 = st.columns([1, 2, 3])

        with col1:
            agg_type = st.selectbox(
                "Tipo de agregación",
                options=["sum", "mean", "percentil_10", "percentil_25", "percentil_50", "percentil_75", "percentil_90", "percentil_100"]
            )

            agg_functions = {
                "sum": "sum",
                "mean": "mean",
                "percentil_10": lambda x: np.percentile(x, 10),
                "percentil_25": lambda x: np.percentile(x, 25),
                "percentil_50": lambda x: np.percentile(x, 50),
                "percentil_75": lambda x: np.percentile(x, 75),
                "percentil_90": lambda x: np.percentile(x, 90),
                "percentil_100": lambda x: np.percentile(x, 100)
            }

            st.markdown(
                """
                <style>
                div[data-baseweb="select"] > div {
                    font-size: 12px !important;
                    color: black !important;
                }
                </style>
                """,
                unsafe_allow_html=True
            )

            meses = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
            weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            with st.expander("Filtros de fecha"):
                meses_seleccionados = st.multiselect("Meses", meses, default=meses)
                weekdays_seleccionados = st.multiselect("Días de la semana", weekdays, default=weekdays)

        data_reset = data_base.reset_index(drop=True)
        results_reset = results.reset_index(drop=True)

        n = min(len(data_reset), len(results_reset))
        data_reset = data_reset.iloc[:n]
        results_reset = results_reset.iloc[:n]

        results_aux = pd.DataFrame(index=range(n))
        results_aux["Periodo"] = data_reset["Period"]
        results_aux["Mes"] = data_reset["Month num"]
        results_aux["Hora"] = data_reset["HourOfDay"]
        results_aux["Date&Time"] = pd.to_datetime(results_reset["Date&Time"])
        results_aux["Weekday"] = results_aux["Date&Time"].dt.day_name()
        results_aux["MWh PV Direct SC"] = np.where(results_reset["Producción PV"] > results_reset["Demanda"], results_reset["Demanda"], results_reset["Producción PV"])
        results_aux["MWh Charge from PV"] = results_reset["Carga de PV"]
        results_aux["MWh BESS Discharge"] = results_reset["Descarga"]
        results_aux["MWh Unmet Demand after BESS"] = results_reset["Cobertura red"]
        results_aux["MWh Unstored Surplus"] = np.where(results_reset["Producción PV"] > (results_reset["Demanda"] + results_reset["Carga de PV"]), results_reset["Producción PV"] - (results_reset["Demanda"] + results_reset["Carga de PV"]), 0)
        results_aux["MWh Charge from Grid"] = results_reset["Carga de red"]
        results_aux["Grid Charging Price"] = results_reset["Precio Carga Red"]
        results_aux["PV Charging Price"] = results_reset["Precio Carga PV"]

        data_period = results_aux[results_aux["Mes"].isin(meses_seleccionados) & results_aux["Weekday"].isin(weekdays_seleccionados)]
        mwh_period = data_period.groupby("Periodo")[mwh_cols].agg(agg_functions[agg_type]).reset_index()
        mwh_hora = data_period.groupby("Hora")[mwh_cols].agg(agg_functions[agg_type]).reset_index()
        if agg_type == "sum":
            price_period = data_period.groupby("Periodo")[price_cols].agg(agg_functions["mean"]).reset_index()
            price_hora = data_period.groupby("Hora")[price_cols].agg(agg_functions["mean"]).reset_index()
        else:
            price_period = data_period.groupby("Periodo")[price_cols].agg(agg_functions[agg_type]).reset_index()
            price_hora = data_period.groupby("Hora")[price_cols].agg(agg_functions[agg_type]).reset_index()

        with col2:

            fig_2 = go.Figure()

            for col in mwh_cols:
                fig_2.add_trace(go.Bar(x=mwh_period["Periodo"], y=mwh_period[col], name=col, marker_color=colors.get(col), yaxis="y1"))

            for col in price_cols:
                fig_2.add_trace(go.Scatter(x=price_period["Periodo"], y=price_period[col], name=col, mode="lines", line=dict(color=colors.get(col), width=2), yaxis="y2"))

            fig_2.update_layout(
                barmode="stack",
                height=300,
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                margin=dict(t=40, b=40, l=50, r=50),
                xaxis=dict(title="Periodo"),
                yaxis=dict(title="Energy (MWh)", showgrid=True),
                yaxis2=dict(title="Price (€/MWh)", overlaying="y", side="right", showgrid=False),
                showlegend=False
            )

            st.plotly_chart(fig_2, use_container_width=True, key="period_mix")

        with col3:
            fig_3 = go.Figure()

            for col in mwh_cols:
                fig_3.add_trace(go.Bar(x=mwh_hora["Hora"], y=mwh_hora[col], name=col, marker_color=colors.get(col), yaxis="y1"))

            for col in price_cols:
                fig_3.add_trace(go.Scatter(x=price_hora["Hora"], y=price_hora[col], name=col, mode="lines", line=dict(color=colors.get(col), width=2), yaxis="y2"))

            fig_3.update_layout(
                barmode="stack",
                height=300,
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                margin=dict(t=40, b=40, l=50, r=50),
                xaxis=dict(title="Hora"),
                yaxis=dict(title="Energy (MWh)", showgrid=True),
                yaxis2=dict(title="Price (€/MWh)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="v", y=1, yanchor="top", x=1.2, xanchor="left", font=dict(size=10), borderwidth=0)
            )

            st.plotly_chart(fig_3, use_container_width=True, key="hora_mix")

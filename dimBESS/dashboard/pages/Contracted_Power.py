import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aux_functions
import dimBESS
import theme
from scenario_selector import require_scenario, scenario_data_base

st.set_page_config(
    page_title="BESS Dashboard - Contracted Power",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Contracted Power")

results, inputs, scenario, scenario_name = require_scenario()
strategy = scenario["Surplus Strategy"]
st.caption(f"Scenario: **{scenario_name}** · Strategy: **{strategy}**")

data_base = scenario_data_base(scenario_name)
if data_base is None:
    st.info("No base hourly data available (go back to Homepage).")
    st.stop()

# The hourly data and the dispatch must come from the same Excel. If they do not (e.g. the Excel loaded in
# Homepage is not the one the scenario was solved with), every capacity figure below is meaningless.
_n = min(len(data_base), len(results))
_demand_ok = np.allclose(
    data_base["Power demand kWh"].values[:_n]/1000, np.asarray(results["Demanda"].values[:_n], dtype=float), rtol=1e-6, atol=1e-6
)
if not _demand_ok:
    st.error(
        "The hourly data loaded in this session (Homepage) are NOT the ones this scenario was solved with: demand differs. "
        "Reload the Excel in Homepage and press 'Recalcular todo' before using this page."
    )
    st.stop()

delta_power = st.slider(
    "Δ Contracted power (MW)",
    min_value=-2.0, max_value=5.0, value=0.0, step=0.1,
    help="Sensitivity for the 'Charging Capacity' and 'Hourly Headroom' tabs: recomputes capacity and headroom with the "
         "current dispatch, without re-solving it. For the effect on savings, use 'Marginal Value'."
)

by_period, hourly = aux_functions.contracted_power_analysis(results, data_base, inputs, delta_power=delta_power, strategy=strategy)


def chart_title(text):
    st.markdown(aux_functions.chart_title(text, bg_color=theme.CORAL_TINT), unsafe_allow_html=True)


def fmt(cols, decimals):
    return {c: f"{{:,.{decimals}f}}" for c in cols}


def ratio(num, den):
    return num/den*100 if den else np.nan


def with_total(table, total):
    """Adds the 'All periods' row (computed from sums, not from averages of percentages)."""
    return pd.concat([table, pd.DataFrame([total], index=["All periods"])])


WINDOW_NOTE = (
    "BESS charging hours = hours inside the charging window used by the dispatch: from 00:00 up to 15:00 "
    "(Solve (PBI logic)) or 16:00 (other strategies), extended to the last hour with PV surplus of that day. "
    "The window therefore moves slightly from day to day."
)

tab_capacity, tab_headroom, tab_marginal = st.tabs(["Charging Capacity", "Hourly Headroom", "Marginal Value"])

bp = by_period
tot = bp.sum(numeric_only=True)

# =====================================================================
# Charging Capacity
# =====================================================================
with tab_capacity:
    st.caption(WINDOW_NOTE)

    # ---- Consistency check: grid charge can never exceed the headroom left by customer demand ----
    n_nan_contract = int(hourly["Potencia contratada (MW)"].isna().sum())
    in_window = hourly[hourly["En ventana"]]
    violations = in_window[in_window["Carga red real (MWh)"] > in_window["Hueco (MW)"] + 1e-6]
    outside = hourly[(~hourly["En ventana"]) & (hourly["Carga red real (MWh)"] > 1e-6)]
    if n_nan_contract:
        st.error(f"{n_nan_contract} hours have no contracted power (NaN): capacity is underestimated. Check the CUPS sheet.")
    if len(violations) or len(outside):
        st.error(
            f"Consistency check failed: {len(violations)} charging hours with grid charge above the headroom left by customer demand"
            f"{' (the Δ contracted power slider is not 0, so capacity was recomputed without re-solving the dispatch)' if delta_power != 0 else ''}"
            f" and {len(outside)} hours with grid charge outside the charging window. See 'Hourly audit' below."
        )
        if len(violations):
            excess = (violations["Carga red real (MWh)"] - violations["Hueco (MW)"])
            summary = pd.DataFrame({
                "Failing hours": violations.groupby("Periodo").size(),
                "Max excess (MW)": excess.groupby(violations["Periodo"]).max(),
                "Avg contracted power (MW)": violations.groupby("Periodo")["Potencia contratada (MW)"].mean(),
                "Avg uncovered demand (MW)": violations.groupby("Periodo")["Demanda no cubierta por PV (MW)"].mean(),
                "Avg grid charge (MWh)": violations.groupby("Periodo")["Carga red real (MWh)"].mean(),
            })
            summary["Peak total grid import (MW)"] = by_period["Pico importación (MW)"]
            summary["Peak import / contracted power (%)"] = by_period["Pico / contrato (%)"]
            st.dataframe(summary.style.format("{:,.2f}", na_rep="-"), width="stretch")
            if (by_period["Pico / contrato (%)"] > 100.5).any():
                st.error(
                    "Total grid import (demand + BESS charge) exceeds the contracted power in these data, which the dispatch "
                    "constraints do not allow (import for demand + grid charge ≤ contracted power in every hour). "
                    "So the dispatch was solved with different inputs than the hourly data loaded now "
                    "(e.g. a different contracted power or demand/PV). Reload the Excel in Homepage and run 'Recalcular todo'."
                )
            st.caption("Failing hours by month: " + ", ".join(f"{int(m)}: {n}" for m, n in violations.groupby("Mes").size().items()))
    else:
        st.success(
            f"Consistency check passed: in all {len(in_window):,} charging hours, grid charge ≤ headroom "
            "(contracted power − uncovered demand), and there is no grid charge outside the charging window."
        )
    if delta_power != 0.0:
        base_period, _ = aux_functions.contracted_power_analysis(results, data_base, inputs, delta_power=0.0, strategy=strategy)
        delta_capacity = bp["Capacidad tras demanda (MWh)"] - base_period["Capacidad tras demanda (MWh)"]
        st.caption("Δ capacity after demand vs current contracted power: " + ", ".join(f"{p} {v:+,.0f} MWh" for p, v in delta_capacity.items()))

    # ---- 1. Capacity vs use -------------------------------------------------
    chart_title("Grid Charging Capacity vs Use in BESS Charging Hours (MWh/year)")
    fig = go.Figure()
    fig.add_bar(x=bp.index, y=bp["Capacidad en ventana (MWh)"], name="Capacity in charging hours", marker_color=theme.NAVY_DARK)
    fig.add_bar(x=bp.index, y=bp["Capacidad tras demanda (MWh)"], name="Capacity after customer demand", marker_color=theme.CHART_CYAN_SOFT)
    fig.add_bar(x=bp.index, y=bp["Carga de red en ventana (MWh)"], name="Grid charge", marker_color=theme.CORAL_DARK)
    fig.update_layout(barmode="group", height=380, xaxis_title="Period", yaxis_title="MWh/year", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Capacity in charging hours = contracted power × charging hours. "
        "Capacity after customer demand = contracted power − demand not covered by PV, summed over charging hours."
    )

    kpi1 = pd.DataFrame({
        "Charging-hours capacity / total capacity (%)": bp["Capacidad en ventana / total (%)"],
        "Grid charge / charging-hours capacity (%)": bp["Carga / capacidad en ventana (%)"],
        "Grid charge / capacity after demand (%)": bp["Carga / capacidad tras demanda (%)"],
    })
    kpi1 = with_total(kpi1, {
        "Charging-hours capacity / total capacity (%)": ratio(tot["Capacidad en ventana (MWh)"], tot["Capacidad total (MWh)"]),
        "Grid charge / charging-hours capacity (%)": ratio(tot["Carga de red en ventana (MWh)"], tot["Capacidad en ventana (MWh)"]),
        "Grid charge / capacity after demand (%)": ratio(tot["Carga de red en ventana (MWh)"], tot["Capacidad tras demanda (MWh)"]),
    })
    st.markdown(
        "#### KPIs · Capacity",
        help="Total capacity = contracted power × all hours of the period in the year. The window share shows how much of it falls "
             "in BESS charging hours. The other two KPIs show how much of the capacity in charging hours (before / after customer "
             "demand) is actually used to charge from the grid."
    )
    st.dataframe(kpi1.style.format("{:,.1f}", na_rep="-"), width="stretch")

    # ---- 2. Import vs max import -------------------------------------------
    chart_title("Grid Import vs Maximum Import in BESS Charging Hours (MWh/year)")
    fig_imp = go.Figure()
    fig_imp.add_bar(x=bp.index, y=bp["Importación demanda ventana (MWh)"], name="For customer demand", marker_color=theme.NAVY_DARK)
    fig_imp.add_bar(x=bp.index, y=bp["Carga de red en ventana (MWh)"], name="For BESS charge", marker_color=theme.CORAL_DARK)
    fig_imp.add_scatter(
        x=bp.index, y=bp["Capacidad en ventana (MWh)"], name="Maximum import (contracted power × charging hours)",
        mode="markers", marker=dict(symbol="line-ew", size=40, line=dict(width=3, color=theme.CHART_CYAN_SOFT))
    )
    fig_imp.update_layout(barmode="stack", height=380, xaxis_title="Period", yaxis_title="MWh/year", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig_imp, width="stretch")
    st.caption(
        "Energy taken from the grid during BESS charging hours: customer demand after PV and BESS, plus BESS charge. "
        "The marker is the maximum importable with the contracted power."
    )

    n_win = bp["Horas en ventana"]
    kpi2 = pd.DataFrame({
        "Avg spare capacity per charging hour (MW)": bp["Capacidad libre media (MW)"],
        "Spare capacity / maximum import (%)": bp["Capacidad libre / máxima (%)"],
        "# Charging hours with spare capacity": bp["Horas de ventana con hueco"],
    })
    kpi2 = with_total(kpi2, {
        "Avg spare capacity per charging hour (MW)": (bp["Capacidad libre media (MW)"]*n_win).sum()/n_win.sum() if n_win.sum() else np.nan,
        "Spare capacity / maximum import (%)": ratio(
            (bp["Capacidad en ventana (MWh)"] - bp["Importación total ventana (MWh)"]).clip(lower=0).sum(), tot["Capacidad en ventana (MWh)"]
        ),
        "# Charging hours with spare capacity": tot["Horas de ventana con hueco"],
    })
    st.markdown(
        "#### KPIs · Spare capacity",
        help="Spare capacity = contracted power − total grid import (customer demand + BESS charge), in charging hours. "
             "# Charging hours with spare capacity = charging hours that are not saturated (the opposite of the chart below)."
    )
    st.dataframe(
        kpi2.style.format({
            "Avg spare capacity per charging hour (MW)": "{:,.2f}",
            "Spare capacity / maximum import (%)": "{:,.1f}",
            "# Charging hours with spare capacity": "{:,.0f}",
        }, na_rep="-"),
        width="stretch"
    )

    # ---- 3. Saturation ------------------------------------------------------
    sat_base = st.radio(
        "Percentage over", ["BESS charging hours", "Hours with grid charge", "Hours with any charge (grid or PV)"], horizontal=True,
        help="'BESS charging hours': all hours of the charging window. 'Hours with grid charge': only the hours where the BESS "
             "actually charges from the grid, i.e. how many of the times it tries to charge end up saturating the contract. "
             "'Hours with any charge (grid or PV)': every hour the BESS charges, from either source, so a lot of PV charging "
             "(which does not use contracted power) dilutes the saturation."
    )
    # Same y range for the three bases: otherwise the axis rescales when switching and the bars look like they grow or shrink.
    sat_ymax = float(np.nanmax(bp[["Saturación ventana (%)", "Saturación / horas con carga (%)", "Saturación / horas con carga total (%)"]].values))
    sat_ymax = min(100.0, np.ceil(sat_ymax*1.15/5)*5) if np.isfinite(sat_ymax) and sat_ymax > 0 else 100.0

    if sat_base == "BESS charging hours":
        chart_title("Saturated Charging Hours (% of BESS charging hours)")
        fig_sat = go.Figure()
        fig_sat.add_bar(
            x=bp.index, y=bp["Saturación por demanda (%)"], name="Customer demand only (no BESS charge)", marker_color=theme.NAVY_DARK,
            customdata=bp["Horas saturadas por demanda"], hovertemplate="%{y:.1f}% · %{customdata:,.0f} h<extra>Customer demand only</extra>"
        )
        fig_sat.add_bar(
            x=bp.index, y=bp["Saturación con carga BESS (%)"], name="With BESS charge", marker_color=theme.CORAL_DARK,
            customdata=bp["Horas saturadas con carga BESS"], hovertemplate="%{y:.1f}% · %{customdata:,.0f} h<extra>With BESS charge</extra>"
        )
        fig_sat.add_scatter(
            x=bp.index, y=bp["Saturación ventana (%)"], mode="text", showlegend=False, textposition="top center",
            text=[f"{p:.1f}% · {h:,.0f} h" if pd.notna(p) else f"{h:,.0f} h" for h, p in zip(bp["Horas saturadas (ventana)"], bp["Saturación ventana (%)"])],
            hoverinfo="skip"
        )
        fig_sat.update_layout(
            barmode="stack", height=380, xaxis_title="Period", yaxis_title="% of charging hours",
            margin=dict(l=60, r=40, t=30, b=50)
        )
        fig_sat.update_yaxes(ticksuffix="%", range=[0, sat_ymax])
        st.plotly_chart(fig_sat, width="stretch")
        st.caption(
            "Saturated = grid import equals the contracted power (1 kW tolerance). 'With BESS charge' hours are those where extra "
            "contracted power could allow more arbitrage; 'customer demand only' hours are saturated by the customer's own consumption."
        )
    else:
        any_charge = sat_base == "Hours with any charge (grid or PV)"
        pct_col = "Saturación / horas con carga total (%)" if any_charge else "Saturación / horas con carga (%)"
        den_col = "Horas con carga (red o PV)" if any_charge else "Horas con carga de red (ventana)"
        den_label = "hours with any charge (grid or PV)" if any_charge else "hours with grid charge"
        chart_title(f"Saturated Hours (% of {den_label})")
        fig_sat = go.Figure()
        fig_sat.add_bar(
            x=bp.index, y=bp[pct_col], name="Saturated", marker_color=theme.CORAL_DARK,
            text=[
                f"{p:.1f}% · {s_:,.0f}/{c_:,.0f} h" if pd.notna(p) else "-"
                for p, s_, c_ in zip(bp[pct_col], bp["Horas saturadas con carga BESS"], bp[den_col])
            ],
            textposition="outside"
        )
        fig_sat.update_layout(
            height=380, xaxis_title="Period", yaxis_title=f"% of {den_label}",
            margin=dict(l=60, r=40, t=30, b=50), showlegend=False
        )
        fig_sat.update_yaxes(ticksuffix="%", range=[0, sat_ymax])
        st.plotly_chart(fig_sat, width="stretch")
        if any_charge:
            st.caption(
                "Saturated hours (grid import = contracted power, with grid charge) over every hour the BESS charges, from grid or PV. "
                "Charging from PV does not use contracted power, so a high PV share lowers the percentage: it shows how often the contract "
                "caps the charge relative to all the charging the BESS does. Bar label: saturated hours / hours with any charge."
            )
        else:
            st.caption(
                "Of the charging-window hours where the BESS charges from the grid, the share where grid import reaches the contracted power "
                "(so the contract may be what caps the charge). Bar label: saturated hours / hours with grid charge."
            )

    kpi3 = pd.DataFrame({
        "# Saturated charging hours": bp["Horas saturadas (ventana)"],
        "Saturated / charging hours (%)": bp["Saturación ventana (%)"],
        "# Hours with grid charge": bp["Horas con carga de red (ventana)"],
        "Saturated / hours with grid charge (%)": bp["Saturación / horas con carga (%)"],
        "# Hours with any charge (grid or PV)": bp["Horas con carga (red o PV)"],
        "Saturated / hours with any charge (%)": bp["Saturación / horas con carga total (%)"],
    })
    kpi3 = with_total(kpi3, {
        "# Saturated charging hours": tot["Horas saturadas (ventana)"],
        "Saturated / charging hours (%)": ratio(tot["Horas saturadas (ventana)"], tot["Horas en ventana"]),
        "# Hours with grid charge": tot["Horas con carga de red (ventana)"],
        "Saturated / hours with grid charge (%)": ratio(tot["Horas saturadas con carga BESS"], tot["Horas con carga de red (ventana)"]),
        "# Hours with any charge (grid or PV)": tot["Horas con carga (red o PV)"],
        "Saturated / hours with any charge (%)": ratio(tot["Horas saturadas con carga BESS"], tot["Horas con carga (red o PV)"]),
    })
    st.markdown("#### KPIs · Saturation")
    st.dataframe(
        kpi3.style.format({
            "# Saturated charging hours": "{:,.0f}", "Saturated / charging hours (%)": "{:,.1f}",
            "# Hours with grid charge": "{:,.0f}", "Saturated / hours with grid charge (%)": "{:,.1f}",
            "# Hours with any charge (grid or PV)": "{:,.0f}", "Saturated / hours with any charge (%)": "{:,.1f}",
        }, na_rep="-"),
        width="stretch"
    )

    # ---- Hourly audit ------------------------------------------------------
    with st.expander("Hourly audit"):
        st.caption(
            "One row per hour. 'In charging window' is the binary flag used by every capacity metric. "
            "Capacity in charging hours = contracted power × flag. Capacity after demand = max(contracted power − uncovered demand, 0) × flag. "
            "Grid charge = BESS charge from the grid × flag."
        )
        audit = hourly[[
            "Fecha", "Hora", "Periodo", "En ventana", "Potencia contratada (MW)", "Demanda no cubierta por PV (MW)",
            "Hueco (MW)", "Carga red real (MWh)", "Importación demanda (MW)", "Importación total (MW)",
        ]].rename(columns={
            "Fecha": "Date", "Hora": "Hour", "Periodo": "Period", "En ventana": "In charging window",
            "Potencia contratada (MW)": "Contracted power (MW)", "Demanda no cubierta por PV (MW)": "Uncovered demand (MW)",
            "Hueco (MW)": "Headroom after demand (MW)", "Carga red real (MWh)": "Grid charge (MWh)",
            "Importación demanda (MW)": "Grid import for demand (MW)", "Importación total (MW)": "Total grid import (MW)",
        })
        audit_filter = st.radio("Show", ["Hours with grid charge", "Hours failing the check", "Charging-window hours", "All hours"], horizontal=True)
        if audit_filter == "Hours with grid charge":
            audit = audit[audit["Grid charge (MWh)"] > 1e-6]
        elif audit_filter == "Hours failing the check":
            audit = audit[(audit["Grid charge (MWh)"] > audit["Headroom after demand (MW)"] + 1e-6) | ((~audit["In charging window"]) & (audit["Grid charge (MWh)"] > 1e-6))]
        elif audit_filter == "Charging-window hours":
            audit = audit[audit["In charging window"]]
        st.dataframe(audit.head(5000), width="stretch", hide_index=True)
        st.download_button(
            "Download hourly audit (CSV)", data=audit.to_csv(index=False).encode("utf-8"),
            file_name=f"contracted_power_audit_{scenario_name}.csv", mime="text/csv"
        )

    # ---- Detail -------------------------------------------------------------
    with st.expander("Detailed tables"):
        detail = bp[[
            "Potencia contratada (MW)", "Horas en ventana", "Capacidad (MWh)", "Carga de red (MWh)", "Utilización (%)",
            "Libre (MWh)", "Carga PV (MWh)", "Horas con carga", "Horas limitadas (contrato)", "Horas limitadas (BESS)",
            "Bloqueada por contrato (MWh)",
        ]].rename(columns={
            "Potencia contratada (MW)": "Contracted power (MW)", "Horas en ventana": "Charging hours",
            "Capacidad (MWh)": "Usable capacity (MWh)", "Carga de red (MWh)": "Grid charge (MWh)",
            "Utilización (%)": "Utilization (%)", "Libre (MWh)": "Unused (MWh)", "Carga PV (MWh)": "PV charge (MWh)",
            "Horas con carga": "Hours with grid charge", "Horas limitadas (contrato)": "Hours limited (contract)",
            "Horas limitadas (BESS)": "Hours limited (BESS power)", "Bloqueada por contrato (MWh)": "Blocked by contract (MWh)",
        })
        st.markdown(
            "##### Charging capacity by period",
            help="Usable capacity = Σ min(contracted power − demand after PV, BESS charging power) over charging hours. "
                 "Hours limited (contract): grid charge equals the headroom and the BESS could take more. Hours limited (BESS power): "
                 "charge at full BESS power. Blocked by contract: upper bound of what the contract prevented from charging."
        )
        st.dataframe(detail.style.format("{:,.1f}", na_rep="-"), width="stretch")

        kpi_detail = bp[[
            "Potencia contratada (MW)", "Pico demanda (MW)", "Pico importación (MW)", "Pico / contrato (%)", "Horas al límite",
            "Horas ≥95%", "Horas demanda ≥95%", "Horas demanda > contrato", "Horas sin hueco", "Hueco ≥ BESS (% horas)",
            "Necesaria P50 (MW)", "Necesaria P90 (MW)", "Déficit P90 (MW)",
        ]].rename(columns={
            "Potencia contratada (MW)": "Contracted power (MW)", "Pico demanda (MW)": "Peak demand (MW)",
            "Pico importación (MW)": "Peak import (MW)", "Pico / contrato (%)": "Peak / contract (%)",
            "Horas al límite": "Hours at limit", "Horas ≥95%": "Hours ≥95%", "Horas demanda ≥95%": "Demand hours ≥95%",
            "Horas demanda > contrato": "Demand hours > contract", "Horas sin hueco": "Charging hours without headroom",
            "Hueco ≥ BESS (% horas)": "Headroom ≥ BESS power (% of charging hours)",
            "Necesaria P50 (MW)": "Required P50 (MW)", "Necesaria P90 (MW)": "Required P90 (MW)", "Déficit P90 (MW)": "P90 shortfall (MW)",
        })
        st.markdown(
            "##### Contracted power KPIs",
            help="Peak import: maximum grid power in the year (demand after PV and BESS + charge). Hours at limit / ≥95%: hours with "
                 "import equal / close to the contracted power. Demand hours ≥95% / > contract: demand not covered by PV close to / above "
                 "the contract (dispatch may be infeasible). Required P50/P90: power needed to charge at full BESS power "
                 "(uncovered demand + BESS power). P90 shortfall: how far the contract is from the required P90."
        )
        st.dataframe(
            kpi_detail.style.format({
                **fmt(["Contracted power (MW)", "Peak demand (MW)", "Peak import (MW)", "Required P50 (MW)", "Required P90 (MW)", "P90 shortfall (MW)"], 2),
                **fmt(["Peak / contract (%)", "Headroom ≥ BESS power (% of charging hours)"], 1),
            }, na_rep="-"),
            width="stretch"
        )

# =====================================================================
# Hourly Headroom
# =====================================================================
STATS = {
    "Mean": "mean", "Median (P50)": 0.5, "P10": 0.1, "P25": 0.25, "P75": 0.75, "P90": 0.9, "P95": 0.95,
    "Max": "max", "Min": "min",
}


PROFILE_COLUMNS = [
    "Importación demanda (MW)", "Carga red real (MWh)", "Hueco libre (MW)", "Potencia contratada (MW)", "Potencia de carga BESS (MW)",
]


def hourly_profile(frame, stat, rank_col="Importación total (MW)"):
    """
    Perfil por hora del día. Con la media se promedia cada serie (la media es lineal: la pila sigue sumando lo mismo que la contratada).
    Con percentil, máximo o mínimo NO se toma el estadístico de cada serie por separado (darían un apilado incoherente): se ordenan los
    días por rank_col (importación total de red, demanda + carga) y, para cada hora, se toma el día que ocupa esa posición con sus
    tres componentes y su potencia contratada, de modo que apilan exactamente la contratada de ese día.
    """

    rows = {}
    for hour, g in frame.groupby("Hora"):
        if stat == "mean":
            rows[hour] = g[PROFILE_COLUMNS].mean()
            continue
        order = g[rank_col].sort_values(kind="stable").index
        n_obs = len(order)
        if stat == "max":
            k = n_obs - 1
        elif stat == "min":
            k = 0
        else:
            k = int(round(stat*(n_obs - 1)))
        rows[hour] = g.loc[order[k], PROFILE_COLUMNS]
    return pd.DataFrame(rows).T


with tab_headroom:
    col_mode, col_stat = st.columns([1, 1])
    mode = col_mode.radio("View", ["All days", "Single day"], horizontal=True)
    if mode == "All days":
        stat_label = col_stat.selectbox(
            "Statistic", list(STATS),
            help="Applied to the contracted-power utilization (grid import for demand + BESS charge, as % of that day's contracted power) "
                 "of each hour of the day over all the days of the year. The chart shows the day at that position with its three components."
        )
        # Contracted power differs by day type (weekday / weekend periods), so there is no single MW reference for "all days":
        # every day is expressed as % of its own contracted power, and the stack always adds up to 100%.
        contract_mw = hourly["Potencia contratada (MW)"].replace(0, np.nan)
        frame = hourly.copy()
        for col in ["Importación demanda (MW)", "Carga red real (MWh)", "Hueco libre (MW)", "Potencia de carga BESS (MW)"]:
            frame[col] = hourly[col]/contract_mw*100
        frame["Importación total (MW)"] = hourly["Importación total (MW)"]/contract_mw*100
        frame["Potencia contratada (MW)"] = 100.0
        unit = "%"
        stat = STATS[stat_label]
        title = f"Hourly Contracted Power Utilization — {stat_label} (% of contracted power)"
        note = (
            f"{stat_label} of each hour of the day over all the days of the year, each day as % of its own contracted power "
            "(the contract differs by day type, so there is no single MW reference). "
            + ("Each series is averaged and the stack adds up to 100%."
               if stat == "mean" else
               "Days are ranked by utilization (grid import for demand + BESS charge); for each hour the chart shows the day at that "
               "position, with its own three components, so they stack up to 100% of that day's contracted power.")
        )
    else:
        dates = sorted(hourly["Fecha"].unique())
        day_sel = col_stat.date_input("Date", value=dates[0], min_value=dates[0], max_value=dates[-1])
        frame = hourly[hourly["Fecha"] == day_sel]
        stat = "mean"
        unit = "MW"
        title = f"Hourly Headroom — {day_sel:%d/%m/%Y} (MW)"
        note = "Hourly values of the selected day. Grid import for demand, grid charge and free headroom stack up to the contracted power."

    if frame.empty:
        st.info("No data for the selection.")
    else:
        profile = hourly_profile(frame, stat)
        fmt_u = "%{y:.1f}%" if unit == "%" else "%{y:.2f} MW"
        prof = {
            "unmet": profile["Importación demanda (MW)"],
            "hueco": profile["Hueco libre (MW)"],
            "contrato": profile["Potencia contratada (MW)"],
            "bess": profile["Potencia de carga BESS (MW)"],
            "carga_red": profile["Carga red real (MWh)"],
        }
        all_hours = sorted(hourly["Hora"].unique())
        prof = {k: v.reindex(all_hours) for k, v in prof.items()}  # hours outside the period stay empty, no fake line
        idx = all_hours
        n_days = frame.groupby("Hora").size().reindex(all_hours)
        hover_days = n_days.fillna(0).astype(int)
        chart_title(title)
        fig_prof = go.Figure()
        fig_prof.add_scatter(
            x=idx, y=prof["unmet"], name="Grid import for demand", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CHART_NAVY), fillcolor="rgba(75,73,155,0.55)",
            customdata=hover_days, hovertemplate="Hour %{x}: " + fmt_u + " (%{customdata} days)<extra>Grid import for demand</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["carga_red"], name="Grid charge", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CORAL_DARK), fillcolor="rgba(214,90,90,0.65)",
            customdata=hover_days, hovertemplate="Hour %{x}: " + fmt_u + " (%{customdata} days)<extra>Grid charge</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["hueco"], name="Free headroom (hypothetical)", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CHART_CYAN_SOFT), fillcolor="rgba(0,180,202,0.35)",
            fillpattern=dict(shape="/", size=7, solidity=0.25, bgcolor="rgba(255,255,255,0)", fgcolor=theme.CHART_CYAN_SOFT),
            customdata=hover_days, hovertemplate="Hour %{x}: " + fmt_u + " (%{customdata} days)<extra>Free headroom (hypothetical)</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["contrato"], name="Contracted power (100%)" if unit == "%" else "Contracted power", mode="lines",
            line=dict(color=theme.NAVY_DARK, width=2, dash="dash")
        )
        fig_prof.add_scatter(
            x=idx, y=prof["bess"], name="BESS power (% of contract)" if unit == "%" else "BESS power", mode="lines",
            line=dict(color=theme.MUTED, width=2, dash="dot")
        )
        fig_prof.update_layout(
            height=400, xaxis_title="Hour of day", margin=dict(l=60, r=40, t=20, b=50),
            legend=dict(orientation="h", y=-0.25),
            yaxis=dict(title="% of contracted power" if unit == "%" else "MW", ticksuffix="%" if unit == "%" else ""),
            xaxis=dict(dtick=1),
        )
        st.plotly_chart(fig_prof, width="stretch")
        st.caption(
            note + " Free headroom (hatched) is hypothetical: contracted power not used by grid import for demand or BESS charge, "
            "i.e. what the BESS could have charged from the grid without exceeding the contract."
        )

    heat_label = stat_label if mode == "All days" else "Mean"
    heat_stat = stat if mode == "All days" else "mean"
    heat_func = (lambda x: x.quantile(heat_stat)) if isinstance(heat_stat, float) else heat_stat
    chart_title(f"Headroom by Hour and Period · {heat_label} (MW)")
    heat = hourly.pivot_table(index="Periodo", columns="Hora", values="Hueco (MW)", aggfunc=heat_func).sort_index()
    fig_heat = go.Figure(
        data=go.Heatmap(
            z=heat.values, x=heat.columns, y=heat.index,
            colorscale=[[0.0, theme.HEATMAP_LIGHT], [1.0, theme.HEATMAP_DARK]],
            colorbar=dict(title="MW"),
            hovertemplate="Period: %{y}<br>Hour: %{x}<br>Headroom: %{z:.2f} MW<extra></extra>"
        )
    )
    fig_heat.update_layout(height=340, xaxis_title="Hour of day", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig_heat, width="stretch")

# =====================================================================
# Marginal Value
# =====================================================================
with tab_marginal:
    st.markdown(
        "#### Marginal Value of Contracted Power",
        help="How much the BESS yearly savings would grow per extra MW of contracted power (water-value style). For the optimization "
             "strategies it is the shadow price of the contracted-power constraint of each daily optimization, obtained in the same solve: "
             "no re-solve and no added power needed. It does not include the power-term cost of contracting more. Independent of the slider above."
    )

    def render_resolve(marginal, step_mw):
        """Savings and charging KPIs obtained by re-solving the dispatch with added power."""
        shown = marginal.drop(index="Base")
        chart_title(f"Marginal Value of +{step_mw:g} MW by Re-solving (€/MW·year)")
        fig_m = go.Figure()
        fig_m.add_bar(
            x=shown.index, y=shown["Valor marginal (€ por MW y año)"],
            marker_color=[theme.NAVY_DARK if i == "Todos" else theme.CORAL_DARK for i in shown.index],
            text=[f"{v:,.0f}" for v in shown["Valor marginal (€ por MW y año)"]], textposition="outside"
        )
        fig_m.update_layout(height=380, xaxis_title="Period increased", margin=dict(l=60, r=40, t=30, b=50))
        fig_m.update_xaxes(ticktext=["All" if i == "Todos" else i for i in shown.index], tickvals=list(shown.index))
        st.plotly_chart(fig_m, width="stretch")
        st.caption(
            "'All' adds the power to the six periods at once (value per MW of uniform increase). Periods are not additive: a day mixes "
            "periods and the dispatch reacts to all of them at once."
        )

        if "KPI Charging Optimization" in marginal.columns:
            chart_title(f"Charging KPIs vs +{step_mw:g} MW Contracted Power")
            fig_k = go.Figure()
            fig_k.add_bar(
                x=shown.index, y=shown["Δ KPI Charging Optimization (pp)"], name="Δ KPI Charging Optimization (pp)",
                marker_color=theme.CHART_CYAN_SOFT
            )
            fig_k.add_bar(
                x=shown.index, y=shown["Δ # Charging hours / Day"], name="Δ # Charging hours / Day", marker_color=theme.NAVY_DARK
            )
            fig_k.update_layout(barmode="group", height=340, xaxis_title="Period increased", margin=dict(l=60, r=40, t=20, b=50))
            fig_k.update_xaxes(ticktext=["All" if i == "Todos" else i for i in shown.index], tickvals=list(shown.index))
            st.plotly_chart(fig_k, width="stretch")
            st.caption(
                "KPI Charging Optimization = (1 / charging hours per day) / C-factor: it rises when the BESS concentrates the same "
                "charge in fewer, more powerful hours. More contracted power lets it charge closer to full power."
            )

        columns = [
            "€ Savings from BESS", "Δ Savings (€/año)", "Valor marginal (€ por MW y año)",
            "Δ Descarga (MWh)", "Δ Carga red (MWh)", "Δ Carga PV (MWh)",
        ]
        names = {
            "€ Savings from BESS": "Savings (€/year)", "Δ Savings (€/año)": "Δ Savings (€/year)",
            "Valor marginal (€ por MW y año)": "€/MW·year", "Δ Descarga (MWh)": "Δ Discharge (MWh)",
            "Δ Carga red (MWh)": "Δ Grid charge (MWh)", "Δ Carga PV (MWh)": "Δ PV charge (MWh)",
            "# Charging hours / Day": "# Charging hours / Day", "KPI Charging Optimization": "KPI Charging Optimization (%)",
            "Δ # Charging hours / Day": "Δ # Charging hours / Day", "Δ KPI Charging Optimization (pp)": "Δ KPI Charging Optimization (pp)",
        }
        if "KPI Charging Optimization" in marginal.columns:
            columns += ["# Charging hours / Day", "Δ # Charging hours / Day", "KPI Charging Optimization", "Δ KPI Charging Optimization (pp)"]
        table = marginal[columns].rename(columns=names, index={"Todos": "All"})
        st.dataframe(table.style.format("{:,.2f}"), width="stretch")

    cache = st.session_state.setdefault("contracted_power_marginal", {})

    # ---- Shadow price of the contracted-power constraint (instant, from the solve itself) ----
    if "Valor marginal (€/MW)" in hourly.columns:
        shadow = hourly["Valor marginal (€/MW)"].fillna(0.0)
        by_per = pd.DataFrame({
            "Marginal value (€/MW·year)": shadow.groupby(hourly["Periodo"]).sum(),
            "Binding hours": (shadow > 1e-9).groupby(hourly["Periodo"]).sum(),
        })
        by_per["Avg value per binding hour (€/MW·h)"] = by_per["Marginal value (€/MW·year)"]/by_per["Binding hours"].replace(0, np.nan)
        total_value = by_per["Marginal value (€/MW·year)"].sum()
        by_per["% of total"] = by_per["Marginal value (€/MW·year)"]/total_value*100 if total_value else np.nan
        by_per_all = with_total(by_per, {
            "Marginal value (€/MW·year)": total_value,
            "Binding hours": by_per["Binding hours"].sum(),
            "Avg value per binding hour (€/MW·h)": total_value/by_per["Binding hours"].sum() if by_per["Binding hours"].sum() else np.nan,
            "% of total": 100.0 if total_value else np.nan,
        })

        chart_title("Marginal Value of Contracted Power by Period — Shadow Price (€/MW·year)")
        fig_s = go.Figure()
        fig_s.add_bar(
            x=by_per.index, y=by_per["Marginal value (€/MW·year)"], marker_color=theme.CORAL_DARK,
            text=[f"{v:,.0f}" for v in by_per["Marginal value (€/MW·year)"]], textposition="outside",
            customdata=by_per["Binding hours"], hovertemplate="%{y:,.0f} €/MW·year · %{customdata:,.0f} binding hours<extra></extra>"
        )
        fig_s.update_layout(height=380, xaxis_title="Period", yaxis_title="€/MW·year", margin=dict(l=60, r=40, t=30, b=50), showlegend=False)
        st.plotly_chart(fig_s, width="stretch")
        st.caption(
            "Savings gained per extra MW of contracted power held all year in that period (first-order estimate, no re-solve). "
            f"All periods together: {total_value:,.0f} €/MW·year. Periods add up only approximately, and the value is exact for small "
            "increments: check it with a re-solve below."
        )
        st.dataframe(
            by_per_all.style.format({
                "Marginal value (€/MW·year)": "{:,.0f}", "Binding hours": "{:,.0f}",
                "Avg value per binding hour (€/MW·h)": "{:,.1f}", "% of total": "{:,.1f}",
            }, na_rep="-"),
            width="stretch"
        )

        chart_title("Shadow Price by Hour and Period — Mean over Days (€/MW·h)")
        heat_sh = hourly.assign(_v=shadow).pivot_table(index="Periodo", columns="Hora", values="_v", aggfunc="mean").sort_index()
        fig_hs = go.Figure(
            data=go.Heatmap(
                z=heat_sh.values, x=heat_sh.columns, y=heat_sh.index,
                colorscale=[[0.0, theme.HEATMAP_LIGHT], [1.0, theme.HEATMAP_DARK]],
                colorbar=dict(title="€/MW·h"),
                hovertemplate="Period: %{y}<br>Hour: %{x}<br>Mean shadow price: %{z:.1f} €/MW·h<extra></extra>"
            )
        )
        fig_hs.update_layout(height=340, xaxis_title="Hour of day", margin=dict(l=60, r=40, t=20, b=50))
        st.plotly_chart(fig_hs, width="stretch")
        st.caption(
            "Where the contracted power constraint binds and what an extra MW would be worth in that hour, averaged over all days "
            "(days where it does not bind count as 0)."
        )

    elif strategy == "Solve (PBI logic)":
        # Rule-based simulation: there is no constraint to take a dual from, but one run takes <1 s, so the sensitivity is computed
        # automatically (+1 MW) instead of asking for a button.
        st.caption(
            "Solve (PBI logic) is a rule-based simulation, not an optimization, so there is no shadow price. The marginal value comes from "
            "re-running the simulation with +1 MW (about a second per case). With this strategy the energy charged each day is set by the "
            "night demand: more power does not charge more energy, it only allows charging in cheaper hours."
        )
        auto_key = ("auto", scenario_name)
        if auto_key not in cache:
            with st.spinner("Running the simulation with +1 MW..."):
                try:
                    cache[auto_key] = dimBESS.contracted_power_marginal_value(data_base, scenario, step_mw=1.0, n_workers=1)
                except RuntimeError as e:
                    st.error(str(e))
        if auto_key in cache:
            render_resolve(cache[auto_key], 1.0)

    else:
        st.info(
            "This scenario was solved before shadow prices were available. Press 'Recalcular todo' in Homepage to solve it again: "
            "the marginal value of the contracted power is then obtained in the same solve."
        )

    # ---- Optional validation by re-solving with added power ----
    with st.expander("Validate by re-solving with added power"):
        if strategy == "Solve (PBI logic)":
            st.caption("The simulation is fast: the table above already uses +1 MW. Use this to try another step.")
        else:
            st.caption(
                "Re-solves the year for a base case, one case per period (+MW only there) and one with all periods at once: it can take a "
                "few minutes. The finite difference is slightly below the shadow price (the value per MW decreases with more power)."
            )
        step_mw = st.number_input("Added power (MW)", min_value=0.1, max_value=10.0, value=1.0, step=0.5)
        cache_key = (scenario_name, float(step_mw))

        if st.button("Calculate"):
            progress = st.progress(0.0, text="Solving cases...")

            def _progress(done, total):
                progress.progress(done/total, text=f"Solving cases... {done}/{total}")

            try:
                cache[cache_key] = dimBESS.contracted_power_marginal_value(
                    data_base, scenario, step_mw=float(step_mw), progress_cb=_progress
                )
            except RuntimeError as e:
                st.error(str(e))
            progress.empty()

        if cache_key in cache:
            render_resolve(cache[cache_key], float(step_mw))

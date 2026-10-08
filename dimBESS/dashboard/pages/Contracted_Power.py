import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import aux_functions
import dimBESS
import theme
from scenario_selector import require_scenario

st.set_page_config(
    page_title="BESS Dashboard - Contracted Power",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Contracted Power")

results, inputs, scenario, scenario_name = require_scenario()
strategy = scenario["Surplus Strategy"]
st.caption(f"Escenario: **{scenario_name}** · Estrategia: **{strategy}**")

data_base = st.session_state.get("data_base")
if data_base is None:
    st.info("No hay datos horarios base disponibles (vuelve a Homepage).")
    st.stop()

delta_power = st.slider(
    "Δ Potencia contratada (MW)",
    min_value=-2.0, max_value=5.0, value=0.0, step=0.1,
    help="Sensibilidad sobre las pestañas 'Charging Capacity' y 'Hourly Headroom': recalcula capacidad y hueco con la "
         "carga real actual, sin volver a resolver el despacho. Para el efecto sobre el ahorro, usa 'Marginal Value'."
)

by_period, hourly = aux_functions.contracted_power_analysis(results, data_base, inputs, delta_power=delta_power, strategy=strategy)


def chart_title(text):
    st.markdown(aux_functions.chart_title(text, bg_color=theme.CORAL_TINT), unsafe_allow_html=True)


def fmt(cols, decimals):
    return {c: f"{{:,.{decimals}f}}" for c in cols}


tab_capacity, tab_headroom, tab_marginal = st.tabs(["Charging Capacity", "Hourly Headroom", "Marginal Value"])

# =====================================================================
# Charging Capacity
# =====================================================================
with tab_capacity:
    if delta_power != 0.0:
        base_period, _ = aux_functions.contracted_power_analysis(results, data_base, inputs, delta_power=0.0, strategy=strategy)
        delta_capacity = by_period["Capacidad (MWh)"] - base_period["Capacidad (MWh)"]
        st.caption("Δ capacidad frente a la potencia actual: " + ", ".join(f"{p} {v:+,.0f} MWh" for p, v in delta_capacity.items()))

    chart_title("Grid Charging Capacity vs Use (MWh/year)")
    fig = go.Figure()
    fig.add_bar(x=by_period.index, y=by_period["Capacidad (MWh)"], name="Capacidad", marker_color=theme.CHART_NAVY_LIGHT)
    fig.add_bar(x=by_period.index, y=by_period["Carga de red (MWh)"], name="Carga de red", marker_color=theme.CORAL_DARK)
    fig.update_layout(barmode="group", height=380, xaxis_title="Periodo", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Capacidad = Σ min(hueco, potencia BESS) en las horas de la ventana de carga. "
        "Hueco = potencia contratada − demanda no cubierta por PV."
    )

    chart_title("Grid Import vs Maximum Import by Period (MWh/year)")
    fig_imp = go.Figure()
    fig_imp.add_bar(x=by_period.index, y=by_period["Importación demanda (MWh)"], name="Para demanda del cliente", marker_color=theme.NAVY_DARK)
    fig_imp.add_bar(x=by_period.index, y=by_period["Carga de red (MWh)"], name="Para carga BESS", marker_color=theme.CORAL_DARK)
    fig_imp.add_scatter(
        x=by_period.index, y=by_period["Importación máxima (MWh)"], name="Máximo (contratada × horas del periodo)",
        mode="markers", marker=dict(symbol="line-ew", size=40, line=dict(width=3, color=theme.CHART_CYAN_SOFT))
    )
    fig_imp.update_layout(barmode="stack", height=380, xaxis_title="Periodo", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig_imp, width="stretch")
    st.caption(
        "Energía tomada de red en el año (demanda del cliente tras PV y BESS, más carga del BESS) frente al máximo importable: "
        "potencia contratada × todas las horas del periodo."
    )

    chart_title("Saturated Hours in Charging Window (% of window hours)")
    fig_sat = go.Figure()
    fig_sat.add_bar(
        x=by_period.index, y=by_period["Saturación ventana (%)"], marker_color=theme.CORAL_DARK,
        text=[f"{p:.1f}% · {h:,.0f} h" if pd.notna(p) else f"{h:,.0f} h" for h, p in zip(by_period["Horas saturadas (ventana)"], by_period["Saturación ventana (%)"])],
        textposition="outside", name="Saturación"
    )
    fig_sat.update_layout(
        height=380, xaxis_title="Periodo", yaxis_title="% de horas de ventana",
        margin=dict(l=60, r=40, t=30, b=50), showlegend=False
    )
    fig_sat.update_yaxes(ticksuffix="%", rangemode="tozero")
    st.plotly_chart(fig_sat, width="stretch")
    st.caption(
        "Porcentaje de las horas de ventana de carga del periodo en las que la importación de red alcanza la potencia contratada "
        "(sobre la barra, también las horas al año). Al ser un porcentaje, los periodos son comparables aunque tengan distinto número de horas."
    )

    st.markdown(
        "#### Charging Capacity by Period",
        help="Ventana de carga: horas del día en que el despacho permite cargar (hasta las 15:00/16:00 o la última hora con "
             "excedente PV). Utilización = carga de red / capacidad. Libre = capacidad − carga de red. Limitadas (contrato): "
             "se carga exactamente el hueco y la batería admitiría más. Limitadas (BESS): se carga a la potencia máxima de la "
             "batería. Bloqueada por contrato: tope superior de lo que el contrato ha impedido cargar. Carga PV: no consume "
             "capacidad de red (salvo en Solve (PBI logic), donde PBI también la limita)."
    )
    cols_capacity = [
        "Potencia contratada (MW)", "Horas en ventana", "Capacidad (MWh)", "Carga de red (MWh)", "Utilización (%)",
        "Libre (MWh)", "Carga PV (MWh)", "Horas con carga", "Horas limitadas (contrato)", "Horas limitadas (BESS)",
        "Bloqueada por contrato (MWh)",
    ]
    st.dataframe(
        by_period[cols_capacity].style.format({
            **fmt(["Potencia contratada (MW)"], 2),
            **fmt(["Capacidad (MWh)", "Carga de red (MWh)", "Utilización (%)", "Libre (MWh)", "Carga PV (MWh)", "Bloqueada por contrato (MWh)"], 1),
        }, na_rep="-"),
        width="stretch"
    )

    st.markdown(
        "#### Contracted Power KPIs",
        help="Pico demanda: máxima demanda sin cubrir por PV. Pico importación: máxima potencia tomada de red (demanda tras PV "
             "y batería + carga). Horas al límite / ≥95%: horas con importación igual / cercana a la potencia contratada. "
             "Horas demanda ≥95% / > contrato: demanda sin cubrir por PV cerca de / por encima del contrato (en este caso el "
             "despacho puede ser infactible). Horas sin hueco y Hueco ≥ BESS (% horas): en la ventana de carga, horas sin "
             "nada de hueco y porcentaje con hueco para cargar a plena potencia. Necesaria P50/P90: potencia que haría falta "
             "para cargar a plena potencia (demanda sin cubrir + potencia BESS). Déficit P90: lo que le falta a la contratada "
             "para llegar a la necesaria P90."
    )
    cols_kpi = [
        "Potencia contratada (MW)", "Pico demanda (MW)", "Pico importación (MW)", "Pico / contrato (%)", "Horas al límite",
        "Horas ≥95%", "Horas demanda ≥95%", "Horas demanda > contrato", "Horas sin hueco", "Hueco ≥ BESS (% horas)",
        "Necesaria P50 (MW)", "Necesaria P90 (MW)", "Déficit P90 (MW)",
    ]
    st.dataframe(
        by_period[cols_kpi].style.format({
            **fmt(["Potencia contratada (MW)", "Pico demanda (MW)", "Pico importación (MW)", "Necesaria P50 (MW)", "Necesaria P90 (MW)", "Déficit P90 (MW)"], 2),
            **fmt(["Pico / contrato (%)", "Hueco ≥ BESS (% horas)"], 1),
        }, na_rep="-"),
        width="stretch"
    )

# =====================================================================
# Hourly Headroom
# =====================================================================
STATS = {
    "Media": "mean", "Mediana (P50)": 0.5, "P10": 0.1, "P25": 0.25, "P75": 0.75, "P90": 0.9, "P95": 0.95,
    "Máximo": "max", "Mínimo": "min",
}


def hourly_stat(frame, column, stat):
    grouped = frame.groupby("Hora")[column]
    if isinstance(stat, float):
        return grouped.quantile(stat)
    return getattr(grouped, stat)()


with tab_headroom:
    col_mode, col_period, col_stat = st.columns([1, 1, 1])
    mode = col_mode.radio("Vista", ["Estadístico del periodo", "Día concreto"], horizontal=True)
    if mode == "Estadístico del periodo":
        period_sel = col_period.selectbox(
            "Periodo", list(by_period.index),
            index=list(by_period.index).index(by_period["Horas con carga"].idxmax()),
            help="Por defecto, el periodo con más horas de carga desde red."
        )
        stat_label = col_stat.selectbox(
            "Estadístico", list(STATS), help="Se calcula para cada hora del día sobre todos los días del periodo."
        )
        frame = hourly[hourly["Periodo"] == period_sel]
        stat = STATS[stat_label]
        title = f"Hourly Headroom — {period_sel} · {stat_label} (MW)"
        note = (
            f"{stat_label} de cada hora sobre los días del periodo. Los estadísticos se calculan por separado en cada serie, "
            "así que la pila puede no llegar exactamente a la potencia contratada (con la media sí)."
        )
    else:
        dates = sorted(hourly["Fecha"].unique())
        day_sel = col_period.date_input("Fecha", value=dates[0], min_value=dates[0], max_value=dates[-1])
        frame = hourly[hourly["Fecha"] == day_sel]
        stat = "mean"
        title = f"Hourly Headroom — {day_sel:%d/%m/%Y} (MW)"
        period_day = ", ".join(sorted(frame["Periodo"].unique()))
        col_stat.markdown(f"**Periodo(s) del día:** {period_day}")
        note = "Valores horarios del día seleccionado. Demanda sin cubrir, carga de red y hueco libre se apilan hasta la potencia contratada."

    if frame.empty:
        st.info("No hay datos para la selección.")
    else:
        prof = {
            "unmet": hourly_stat(frame, "Demanda no cubierta por PV (MW)", stat),
            "hueco": hourly_stat(frame, "Hueco libre (MW)", stat),
            "contrato": hourly_stat(frame, "Potencia contratada (MW)", stat),
            "bess": hourly_stat(frame, "Potencia de carga BESS (MW)", stat),
            "carga_red": hourly_stat(frame, "Carga red real (MWh)", stat),
        }
        all_hours = sorted(hourly["Hora"].unique())
        prof = {k: v.reindex(all_hours) for k, v in prof.items()}  # horas sin datos en este periodo -> hueco, no línea falsa
        idx = all_hours
        n_days = frame.groupby("Hora").size().reindex(all_hours)
        pct_charging = frame.groupby("Hora")["Carga red real (MWh)"].apply(lambda x: (x > 1e-6).mean()*100).reindex(all_hours)
        hover_days = n_days.fillna(0).astype(int)
        chart_title(title)
        fig_prof = go.Figure()
        if mode == "Estadístico del periodo":
            fig_prof.add_bar(
                x=idx, y=pct_charging, name="% de días con carga de red", yaxis="y2",
                marker_color="rgba(214,90,90,0.18)", hovertemplate="Hora %{x}: %{y:.0f}% de los días con carga<extra></extra>"
            )
        fig_prof.add_scatter(
            x=idx, y=prof["unmet"], name="Demanda sin cubrir", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CHART_NAVY), fillcolor="rgba(75,73,155,0.55)",
            customdata=hover_days, hovertemplate="Hora %{x}: %{y:.2f} MW (%{customdata} días)<extra>Demanda sin cubrir</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["carga_red"], name="Carga de red", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CORAL_DARK), fillcolor="rgba(214,90,90,0.65)",
            customdata=hover_days, hovertemplate="Hora %{x}: %{y:.2f} MW (%{customdata} días)<extra>Carga de red</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["hueco"], name="Hueco libre", mode="lines",
            stackgroup="demanda", line=dict(width=0.5, color=theme.CHART_CYAN_SOFT), fillcolor="rgba(0,180,202,0.35)",
            customdata=hover_days, hovertemplate="Hora %{x}: %{y:.2f} MW (%{customdata} días)<extra>Hueco libre</extra>"
        )
        fig_prof.add_scatter(
            x=idx, y=prof["contrato"], name="Potencia contratada", mode="lines",
            line=dict(color=theme.NAVY_DARK, width=2, dash="dash")
        )
        fig_prof.add_scatter(
            x=idx, y=prof["bess"], name="Potencia BESS", mode="lines",
            line=dict(color=theme.MUTED, width=2, dash="dot")
        )
        fig_prof.update_layout(
            height=400, xaxis_title="Hora del día", margin=dict(l=60, r=60, t=20, b=50),
            legend=dict(orientation="h", y=-0.25),
            yaxis=dict(title="MW"),
            yaxis2=dict(title="% días con carga", overlaying="y", side="right", range=[0, 100], showgrid=False, ticksuffix="%"),
            xaxis=dict(dtick=1),
        )
        st.plotly_chart(fig_prof, width="stretch")
        st.caption(
            note + " Un mismo periodo cubre horas distintas según mes y tipo de día (p. ej. P6 son las noches de todos los días y "
            "los fines de semana completos), así que cada hora se calcula sobre un número distinto de días (se ve al pasar el cursor); "
            "las horas que no pertenecen al periodo quedan vacías. La carga de red ocurre solo en una parte de los días: con la "
            "mediana o percentiles bajos sale 0 en la mayoría de horas; la barra de fondo indica en qué % de los días hay carga."
        )

    heat_label = stat_label if mode == "Estadístico del periodo" else "Media"
    heat_stat = stat if mode == "Estadístico del periodo" else "mean"
    heat_func = (lambda x: x.quantile(heat_stat)) if isinstance(heat_stat, float) else heat_stat
    chart_title(f"Headroom by Hour and Period · {heat_label} (MW)")
    heat = hourly.pivot_table(index="Periodo", columns="Hora", values="Hueco (MW)", aggfunc=heat_func).sort_index()
    fig_heat = go.Figure(
        data=go.Heatmap(
            z=heat.values, x=heat.columns, y=heat.index,
            colorscale=[[0.0, theme.HEATMAP_LIGHT], [1.0, theme.HEATMAP_DARK]],
            colorbar=dict(title="MW"),
            hovertemplate="Periodo: %{y}<br>Hora: %{x}<br>Hueco: %{z:.2f} MW<extra></extra>"
        )
    )
    fig_heat.update_layout(height=340, xaxis_title="Hora del día", margin=dict(l=60, r=40, t=20, b=50))
    st.plotly_chart(fig_heat, width="stretch")

# =====================================================================
# Marginal Value
# =====================================================================
with tab_marginal:
    st.markdown(
        "#### Marginal Value of Contracted Power",
        help="Cuánto sube el ahorro anual del BESS al contratar más potencia (tipo water value). Se re-resuelve el despacho con "
             "la estrategia de este escenario: un caso base, uno por periodo (+MW solo en ese periodo) y uno con todos a la vez. "
             "No incluye el coste del término de potencia de contratar más. Los periodos no son aditivos: un mismo día mezcla "
             "periodos y el despacho reacciona a la vez. Independiente del slider superior."
    )
    if strategy == "Solve (PBI logic)":
        st.caption(
            "Con Solve (PBI logic) el volumen cargado cada día lo fija la demanda nocturna: más potencia no carga más energía, "
            "solo permite cargar en horas más baratas."
        )
    else:
        st.caption("Con estrategias LP se resuelve el año varias veces: puede tardar varios minutos.")

    step_mw = st.number_input("Potencia añadida (MW)", min_value=0.1, max_value=10.0, value=1.0, step=0.5)
    cache = st.session_state.setdefault("contracted_power_marginal", {})
    cache_key = (scenario_name, float(step_mw))

    if st.button("Calcular"):
        progress = st.progress(0.0, text="Resolviendo casos...")

        def _progress(done, total):
            progress.progress(done/total, text=f"Resolviendo casos... {done}/{total}")

        try:
            cache[cache_key] = dimBESS.contracted_power_marginal_value(
                data_base, scenario, step_mw=float(step_mw), progress_cb=_progress
            )
        except RuntimeError as e:
            st.error(str(e))
        progress.empty()

    marginal = cache.get(cache_key)
    if marginal is not None:
        shown = marginal.drop(index="Base")
        chart_title(f"Marginal Value of +{step_mw:g} MW (€/MW·year)")
        fig_m = go.Figure()
        fig_m.add_bar(
            x=shown.index, y=shown["Valor marginal (€ por MW y año)"],
            marker_color=[theme.NAVY_DARK if i == "Todos" else theme.CORAL_DARK for i in shown.index],
            text=[f"{v:,.0f}" for v in shown["Valor marginal (€ por MW y año)"]], textposition="outside"
        )
        fig_m.update_layout(height=380, xaxis_title="Periodo ampliado", margin=dict(l=60, r=40, t=30, b=50))
        st.plotly_chart(fig_m, width="stretch")
        st.caption("'Todos' añade la potencia en los seis periodos a la vez (valor por MW de subida uniforme).")

        table = marginal[[
            "€ Savings from BESS", "Δ Savings (€/año)", "Valor marginal (€ por MW y año)",
            "Δ Descarga (MWh)", "Δ Carga red (MWh)", "Δ Carga PV (MWh)",
        ]].rename(columns={
            "€ Savings from BESS": "Ahorro (€/año)", "Δ Savings (€/año)": "Δ Ahorro (€/año)",
            "Valor marginal (€ por MW y año)": "€/MW·año",
        })
        st.dataframe(table.style.format("{:,.1f}"), width="stretch")

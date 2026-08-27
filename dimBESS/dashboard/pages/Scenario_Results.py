import pandas as pd
import plotly.graph_objects as go
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

all_results = pd.DataFrame(list(kpi_rows.values()))
if "Client" not in all_results.columns:
    all_results["Client"] = None
all_results["Client"] = all_results["Client"].fillna(all_results["Scenario"].map(dimBESS.client_from_scenario_name))

clients = sorted(all_results["Client"].dropna().unique())
if st.session_state.get("selected_client") not in clients:
    st.session_state["selected_client"] = clients[0]

with st.sidebar:
    st.session_state["selected_client"] = st.selectbox(
        "Cliente",
        options=clients,
        index=clients.index(st.session_state["selected_client"])
    )

selected_client = st.session_state["selected_client"]
client_results = all_results[all_results["Client"] == selected_client].sort_values("BESS Capacity (MWh)")

hy, th = st.session_state.get("kpi_params", (dimBESS.DEFAULT_HORIZON_YEARS, 20.0))
st.caption(f"Cliente: **{selected_client}** · Horizonte: {hy} años · Threshold: {th:.0f}% · resaltado = escenario apto")

styled_results = dimBESS.highlight_results(client_results.reset_index(drop=True))
raw_columns = client_results.columns

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

st.markdown("#### Evolución de ahorros vs capacidad BESS")

x = client_results["BESS Capacity (MWh)"]
labels = [f"{v:.2f} MWh" for v in x]
threshold_col = f"(>{th:.0f}%)"

col_a, col_b = st.columns(2)

with col_a:
    leasing_col = f"€ Leasing {hy}y"
    savings_col = f"€ Total Savings {hy}y"
    net_savings = client_results[savings_col] - client_results[leasing_col]

    fig1 = go.Figure()
    fig1.add_hline(y=0, line=dict(color=theme.MUTED, width=1, dash="dot"))
    fig1.add_trace(go.Scatter(
        x=x, y=client_results[leasing_col], name=f"€ Leasing {hy}y", mode="lines+markers",
        line=dict(color=theme.CHART_NAVY, width=2), marker=dict(size=9),
    ))
    fig1.add_trace(go.Scatter(
        x=x, y=client_results[savings_col], name=f"€ Total Savings {hy}y", mode="lines+markers",
        line=dict(color=theme.CYAN, width=2), marker=dict(size=9),
    ))
    fig1.add_trace(go.Scatter(
        x=x, y=net_savings, name=f"€ Net Savings {hy}y", mode="lines+markers+text",
        line=dict(color=theme.ORANGE, width=2), marker=dict(size=9),
        text=labels, textposition="top center", textfont=dict(size=10, color="grey"),
    ))
    fig1.update_layout(
        title=dict(text=f"Leasing vs Savings a {hy} años (€)", x=0.5, xanchor="center", font=dict(color="grey", size=14)),
        xaxis_title="BESS Capacity (MWh)",
        yaxis_title="€",
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
        hovermode="x unified",
        margin=dict(t=40, b=10, l=10, r=10),
        height=380,
    )
    st.plotly_chart(fig1, width="stretch")

with col_b:
    marker_symbols = ["circle" if apto else "circle-open" for apto in client_results[threshold_col]]

    fig2 = go.Figure()
    fig2.add_hline(
        y=th, line=dict(color=theme.MUTED, width=2, dash="dash"),
        annotation_text="Commercial Threshold", annotation_position="top left",
        annotation_font=dict(color="grey", size=11),
    )
    fig2.add_trace(go.Scatter(
        x=x, y=client_results["% Savings vs Leasing"], mode="lines+markers+text",
        line=dict(color=theme.CYAN, width=2),
        marker=dict(size=10, color=theme.CYAN, symbol=marker_symbols, line=dict(width=2, color=theme.CYAN)),
        text=labels, textposition="top center", textfont=dict(size=10, color="grey"),
        showlegend=False,
    ))
    fig2.update_layout(
        title=dict(text="% Savings vs Leasing", x=0.5, xanchor="center", font=dict(color="grey", size=14)),
        xaxis_title="BESS Capacity (MWh)",
        yaxis_title="% Savings vs Leasing",
        hovermode="x unified",
        margin=dict(t=40, b=10, l=10, r=10),
        height=380,
    )
    st.plotly_chart(fig2, width="stretch")

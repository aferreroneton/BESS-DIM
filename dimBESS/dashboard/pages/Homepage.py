import io
from pathlib import Path

import pandas as pd
import streamlit as st

import dimBESS
import theme

st.set_page_config(
    page_title="BESS Dashboard - Homepage",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Homepage")

DEFAULT_FILE = Path(__file__).resolve().parent.parent.parent / "modelo_dimensionamiento_BESS_inputs_v2.xlsx"

uploaded_file = st.file_uploader(
    "Cargar otro Excel de escenarios (opcional; si no se sube nada se usa el archivo por defecto)",
    type=["xlsx"]
)

# st.file_uploader() puede "perder" el archivo al navegar a otra página del dashboard y
# volver (el widget se reinstancia y devuelve None aunque el usuario ya hubiera subido
# algo), lo que hacía que la app cayera silenciosamente al Excel por defecto y resolviera
# el caso de ejemplo en vez del subido. Persistimos los bytes explícitamente para que
# source_file/source_label no dependan del valor del widget en CADA rerun.
if uploaded_file is not None:
    st.session_state["uploaded_bytes"] = uploaded_file.getvalue()
    st.session_state["uploaded_name"] = uploaded_file.name

if "uploaded_bytes" in st.session_state:
    source_file = io.BytesIO(st.session_state["uploaded_bytes"])
    source_label = st.session_state["uploaded_name"]
else:
    source_file = DEFAULT_FILE
    source_label = DEFAULT_FILE.name

try:
    scenarios = dimBESS.load_scenarios(source_file)
except Exception as e:
    st.error(f"No se pudieron cargar los escenarios de '{source_label}': {e}")
    st.stop()

st.success(f"{len(scenarios)} escenario(s) cargado(s) desde '{source_label}'")

cups_info = dimBESS.read_cups_info(source_file)
st.caption(f"CUPS: **{cups_info['Client']}** · {cups_info['Plant']} · Tarifa **{cups_info['Tariff']}**")

with st.expander("Escenarios definidos"):
    st.dataframe(pd.DataFrame(scenarios))

if "scenario_results" not in st.session_state:
    st.session_state["scenario_results"] = {}
if "kpi_rows" not in st.session_state:
    st.session_state["kpi_rows"] = {}
if "savings_projections" not in st.session_state:
    st.session_state["savings_projections"] = {}
if (
    "scenario_source" not in st.session_state
    or st.session_state["scenario_source"] != source_label
    or "data_base" not in st.session_state
):
    st.session_state["scenario_results"] = {}
    st.session_state["kpi_rows"] = {}
    st.session_state["savings_projections"] = {}
    st.session_state["scenario_source"] = source_label
    st.session_state["source_file"] = source_file
    st.session_state["data_base"] = dimBESS.load_hourly_data(source_file)
    st.session_state["cups_info"] = dimBESS.read_cups_info(source_file)
    st.session_state.pop("extension_data", None)
    st.session_state.pop("leasing_tables", None)

scenario_names = [s["Scenario"] for s in scenarios]
solved_names = list(st.session_state["scenario_results"].keys())
pending_names = [name for name in scenario_names if name not in solved_names]

st.markdown(f"**Resueltos:** {len(solved_names)} / {len(scenario_names)}")

col_h, col_t = st.columns(2)
horizon_years = col_h.number_input(
    "Horizonte (años)", min_value=1, max_value=20, value=dimBESS.DEFAULT_HORIZON_YEARS, step=1,
    help="Se aplica al resolver; para cambiarlo sobre escenarios ya resueltos, usa 'Recalcular todo'."
)
savings_threshold = col_t.number_input("Threshold % Savings vs Leasing", min_value=0.0, value=20.0, step=1.0)

col_run, col_reset = st.columns([1, 1])

with col_run:
    if pending_names:
        if st.button(f"Run Scenarios ({len(pending_names)} pendiente(s))"):
            extra_years = ", ".join(str(y) for y in dimBESS.EXTENDED_STUDY_YEARS if y != 1)
            with st.spinner(
                f"Resolviendo {len(pending_names)} escenario(s) en paralelo (los marcados como "
                f"'Extended study' resuelven también año {extra_years}, "
                f"~{len(dimBESS.EXTENDED_STUDY_YEARS)}x más lento)..."
            ):
                new_scenario_results, new_kpi_rows, new_savings_projections = dimBESS.solve_and_analyze_scenarios(
                    source_file, only=pending_names, horizon_years=horizon_years, savings_threshold=savings_threshold
                )
            st.session_state["scenario_results"].update(new_scenario_results)
            st.session_state["kpi_rows"].update(new_kpi_rows)
            st.session_state["savings_projections"].update(new_savings_projections)
            st.session_state["kpi_params"] = (horizon_years, savings_threshold)
            st.success("Escenario(s) resuelto(s). Resultados y KPIs disponibles en Scenario Results.")
            st.rerun()
    else:
        st.info("Todos los escenarios están resueltos. Ve a cualquier página del dashboard y elige el escenario a visualizar.")

with col_reset:
    if solved_names:
        if st.button("Recalcular todo (forzar re-solve)"):
            st.session_state["scenario_results"] = {}
            st.session_state["kpi_rows"] = {}
            st.session_state["savings_projections"] = {}
            st.rerun()

if solved_names:
    with st.expander("Escenarios ya resueltos"):
        st.write(solved_names)

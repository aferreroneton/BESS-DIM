from pathlib import Path

import pandas as pd
import streamlit as st

import dimBESS
import theme

st.set_page_config(
    page_title="BESS Dashboard - Homepage",
    page_icon=theme.LOGO_IMAGE,
    layout="wide"
)
st.image(theme.LOGO_FULL_PATH, width=280)
st.title("BESS Model")
st.subheader("Homepage")

DEFAULT_FILE = Path(__file__).resolve().parent.parent.parent / "modelo_dimensionamiento_BESS_inputs_v2.xlsx"

uploaded_file = st.file_uploader(
    "Cargar otro Excel de escenarios (opcional; si no se sube nada se usa el archivo por defecto)",
    type=["xlsx"]
)
source_file = uploaded_file if uploaded_file is not None else DEFAULT_FILE
source_label = uploaded_file.name if uploaded_file is not None else DEFAULT_FILE.name

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
if (
    "scenario_source" not in st.session_state
    or st.session_state["scenario_source"] != source_label
    or "data_base" not in st.session_state
):
    st.session_state["scenario_results"] = {}
    st.session_state["scenario_source"] = source_label
    st.session_state["data_base"] = pd.read_excel(source_file, sheet_name="Hourly Data", header=2)
    st.session_state["cups_info"] = dimBESS.read_cups_info(source_file)

scenario_names = [s["Scenario"] for s in scenarios]
solved_names = list(st.session_state["scenario_results"].keys())
pending_names = [name for name in scenario_names if name not in solved_names]

st.markdown(f"**Resueltos:** {len(solved_names)} / {len(scenario_names)}")

col_run, col_reset = st.columns([1, 1])

with col_run:
    if pending_names:
        if st.button(f"Run Scenarios ({len(pending_names)} pendiente(s))"):
            with st.spinner(f"Resolviendo {len(pending_names)} escenario(s) en paralelo..."):
                new_results = dimBESS.solve_all_scenarios(source_file, only=pending_names)
            st.session_state["scenario_results"].update(new_results)
            st.success("Escenario(s) resuelto(s).")
            st.rerun()
    else:
        st.info("Todos los escenarios están resueltos. Ve a cualquier página del dashboard y elige el escenario a visualizar.")

with col_reset:
    if solved_names:
        if st.button("Recalcular todo (forzar re-solve)"):
            st.session_state["scenario_results"] = {}
            st.rerun()

if solved_names:
    with st.expander("Escenarios ya resueltos"):
        st.write(solved_names)

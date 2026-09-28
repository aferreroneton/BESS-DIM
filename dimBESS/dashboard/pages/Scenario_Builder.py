import streamlit as st

import dimBESS
import scenario_builder as sb
import theme

st.set_page_config(
    page_title="BESS Dashboard - Scenario Builder",
    page_icon=theme.logo_image(),
    layout="wide"
)
st.title("BESS Model")
st.subheader("Scenario Builder")

if "data_base" not in st.session_state or "cups_info" not in st.session_state:
    st.warning("Carga un Excel en Homepage primero (necesita la hoja 'Hourly Data' y 'CUPS').")
    st.stop()

cups_info = st.session_state["cups_info"]
st.caption(f"CUPS: **{cups_info['Client']}** · {cups_info['Plant']} · Tarifa **{cups_info['Tariff']}** (fijado en la hoja CUPS del Excel)")

if "scenario_results" not in st.session_state:
    st.session_state["scenario_results"] = {}
if "kpi_rows" not in st.session_state:
    st.session_state["kpi_rows"] = {}
if "savings_projections" not in st.session_state:
    st.session_state["savings_projections"] = {}

col_form, col_preview = st.columns([2, 1])

with col_form:
    st.markdown("#### Definición del escenario")

    r1c1, r1c2, r1c3 = st.columns(3)
    container_type = r1c1.selectbox("Type of Container", sb.CONTAINER_TYPES)
    n_containers = r1c2.number_input("N containers", min_value=1, value=1, step=1)
    client_rating = r1c3.number_input(
        "Client Rating",
        min_value=sb.CLIENT_RATING_MIN,
        max_value=sb.CLIENT_RATING_MAX,
        value=sb.CLIENT_RATING_MAX,
        step=1,
        help=f"Rango soportado por la tabla de Leasing: {sb.CLIENT_RATING_MIN}-{sb.CLIENT_RATING_MAX}"
    )

    r2c1, r2c2 = st.columns(2)
    cycles_day = r2c1.number_input("Cycles/day", min_value=0.5, max_value=5.0, value=1.0, step=0.1)
    c_factor = r2c2.number_input("C-Factor", min_value=0.0, max_value=1.0, value=0.5, step=0.01)

    r3c1, r3c2 = st.columns(2)
    surplus_strategy = r3c1.selectbox("Surplus Strategy", sb.SURPLUS_STRATEGIES)
    price_mode = r3c2.selectbox("Price mode from PV surplus", sb.PRICE_MODES)

    r4c1, r4c2 = st.columns(2)
    ppa_price = r4c1.number_input("PV PPA Price for charging €/MWh", min_value=0.0, value=35.2, step=0.1)
    original_ppa_price = r4c2.number_input("Original PPA price €/MWh", min_value=0.0, value=35.2, step=0.1)

    discharge_cost = st.number_input("Discharge Cost (opcional)", min_value=0.0, value=0.0, step=0.1)

    _extra_years_help = ", ".join(str(y) for y in dimBESS.EXTENDED_STUDY_YEARS if y != 1)
    study_type = st.selectbox(
        "Study Type", sorted(dimBESS.SUPPORTED_STUDY_TYPES),
        help=f"Extended study resuelve también año {_extra_years_help} (proyectados) para una "
             f"curva de ahorro propia del escenario, en vez del modelo de regresión externo. "
             f"~{len(dimBESS.EXTENDED_STUDY_YEARS)}x más lento."
    )

with col_preview:
    st.markdown("#### Vista previa")

    try:
        scenario = sb.build_scenario(
            client=cups_info["Client"],
            plant=cups_info["Plant"],
            tariff=cups_info["Tariff"],
            container_type=container_type,
            n_containers=n_containers,
            client_rating=client_rating,
            cycles_day=cycles_day,
            c_factor=c_factor,
            surplus_strategy=surplus_strategy,
            price_mode=price_mode,
            ppa_price=ppa_price,
            original_ppa_price=original_ppa_price,
            discharge_cost=discharge_cost,
            study_type=study_type,
        )
    except ValueError as e:
        st.error(str(e))
        st.stop()

    st.text_input("Scenario", value=scenario["Scenario"], disabled=True)
    st.metric("Battery size MWh", f"{scenario['Battery size MWh']:.3f}")
    st.metric("Depth of Discharge (DoD) %", f"{scenario['Depth of Discharge (DoD) %']*100:.0f} %")
    st.metric("Battery operational capacity MWh", f"{scenario['Battery operational capacity MWh']:.3f}")
    st.metric("Charge/Discharge capacity per hour MWh", f"{scenario['Charge capacity per hour MWh']:.3f}")
    st.metric("Leasing Scenario", scenario["Leasing Scenario"])
    st.metric("€ Leasing Monthly", f"{scenario['€ Leasing Monthly']:,.0f} €")

already_solved = scenario["Scenario"] in st.session_state["scenario_results"]
if already_solved:
    st.info("Ya existe un escenario resuelto con este mismo nombre; al resolver se sobrescribirá.")

if st.button("Resolver y añadir al dashboard"):
    horizon_years, savings_threshold = st.session_state.get("kpi_params", (dimBESS.DEFAULT_HORIZON_YEARS, 20.0))

    extension_data = None
    y1 = None
    spinner_msg = f"Resolviendo '{scenario['Scenario']}'..."
    if study_type == "Extended study":
        _years_msg = ", ".join(str(y) for y in dimBESS.EXTENDED_STUDY_YEARS)
        spinner_msg = (
            f"Resolviendo '{scenario['Scenario']}' (Extended study: año {_years_msg}, "
            f"~{len(dimBESS.EXTENDED_STUDY_YEARS)}x más lento)..."
        )

    with st.spinner(spinner_msg):
        if study_type == "Extended study":
            # Periodos/precios/curvas no dependen del escenario: se cargan una vez y se
            # reutilizan para cualquier otro escenario Extended study que se añada después.
            if "extension_data" not in st.session_state:
                st.session_state["extension_data"] = dimBESS.load_extension_data(
                    st.session_state["source_file"], cups_info["Tariff"]
                )
            extension_data = st.session_state["extension_data"]
            y1 = int(st.session_state["data_base"]["Year"].dropna().iloc[0])

        if "leasing_tables" not in st.session_state:
            st.session_state["leasing_tables"] = dimBESS.load_leasing_tables(st.session_state["source_file"])
        leasing_tables = st.session_state["leasing_tables"]

        model, results, inputs = dimBESS.solve_scenario(st.session_state["data_base"], scenario)
        kpi_row, savings_by_year = dimBESS.kpi_row_from_results(
            st.session_state["data_base"], scenario, results, inputs,
            horizon_years, savings_threshold, extension_data, y1, leasing_tables
        )

    st.session_state["scenario_results"][scenario["Scenario"]] = {
        "results": results,
        "inputs": inputs,
        "scenario": scenario,
    }
    st.session_state["kpi_rows"][scenario["Scenario"]] = kpi_row
    st.session_state["savings_projections"][scenario["Scenario"]] = savings_by_year
    st.session_state["kpi_params"] = (horizon_years, savings_threshold)
    st.session_state["selected_scenario"] = scenario["Scenario"]
    st.success(f"Escenario '{scenario['Scenario']}' resuelto y añadido (visualización + Scenario Results).")
    st.rerun()

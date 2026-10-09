import streamlit as st


def require_scenario():
    """
    Sidebar selector shared by every visualization page: picks among the
    scenarios already solved and stored in st.session_state["scenario_results"]
    (populated from Homepage's "Run Scenarios" button). Never re-solves anything.

    Returns (results, inputs, scenario, scenario_name) for the selected scenario,
    or stops the page with a warning if nothing has been solved yet.
    """

    scenario_results = st.session_state.get("scenario_results", {})
    if not scenario_results:
        st.warning("No hay escenarios resueltos todavía. Ve a Homepage y pulsa 'Run Scenarios'.")
        st.stop()

    names = list(scenario_results.keys())
    if st.session_state.get("selected_scenario") not in names:
        st.session_state["selected_scenario"] = names[0]

    with st.sidebar:
        st.session_state["selected_scenario"] = st.selectbox(
            "Escenario",
            options=names,
            index=names.index(st.session_state["selected_scenario"])
        )

    selected_name = st.session_state["selected_scenario"]
    entry = scenario_results[selected_name]
    return entry["results"], entry["inputs"], entry["scenario"], selected_name


def scenario_data_base(scenario_name):
    """
    Datos horarios (Hourly Data) con los que se resolvió el escenario. Se guardan junto al
    resultado para que visualización y resultado no puedan venir de Excels distintos; si el
    escenario se resolvió antes de guardarlos, cae al data_base de la sesión (el de Homepage).
    """

    entry = st.session_state.get("scenario_results", {}).get(scenario_name, {})
    data_base = entry.get("data_base")
    return data_base if data_base is not None else st.session_state.get("data_base")

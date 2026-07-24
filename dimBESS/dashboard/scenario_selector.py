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

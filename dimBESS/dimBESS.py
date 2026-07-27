import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np
import pv_first_daily
import best_price_daily
import aux_functions

SAVINGS_MODEL_INTERCEPT = 0.943906
SAVINGS_MODEL_B_YEAR = -0.003315
SAVINGS_MODEL_B_YEAR2 = -0.000697

SAVINGS_MODEL2_INTERCEPT = 0.939796
SAVINGS_MODEL2_B_YEAR = -0.005466
SAVINGS_MODEL2_B_YEAR2 = -0.000866

SAVINGS_MODEL_B_TARIFF = {
    "6.1TD": 0.0,          # categoría de referencia
    "6.2TD": -0.000888,
    "6.3TD": -0.006478,
    "6.4TD": -0.009632,
}

SAVINGS_MODEL2_B_TARIFF = {
    "6.1TD": 0.0,          # categoría de referencia
    "6.2TD": -0.001068,
    "6.3TD": -0.001951,
    # "6.4TD" no disponible en la muestra de calibración -> sin coeficiente,
    # cualquier intento de usar Modelo 2 con 6.4TD debe caer al Modelo 1.
}

PV_DEGRADATION_CURVE = {
    1   :   1.0000,
    2   :   0.9900,
    3   :   0.9870, 
    4   :   0.9840, 
    5   :   0.9810,
    6   :   0.9780,
    7   :   0.9750, 
    8   :   0.9720,
    9   :   0.9690, 
    10  :   0.9660,
    11  :   0.9630, 
    12  :   0.9600, 
    13  :   0.9570, 
    14  :   0.9540, 
    15  :   0.9510,
    16  :   0.9480, 
    17  :   0.9450, 
    18  :   0.9420, 
    19  :   0.9390,     
    20  :   0.9360,
    21  :   0.9330,
}
_PV_DEGRADATION_SLOPE = 0.0030

SAVINGS_MODEL_B_CONTAINER_SOLAX = -0.005208  # 0 para Risen (referencia)

SAVINGS_MODEL2_B_CONTAINER_SOLAX = -0.004761  # 0 para Risen (referencia)
SAVINGS_MODEL2_B_PCT_CHARGE_PV = 0.017502

SAVINGS_MODEL2_PCT_CHARGE_PV_MIN = 0.0
SAVINGS_MODEL2_PCT_CHARGE_PV_MAX = 0.65

SAVINGS_MODEL2_VALID_TARIFFS = set(SAVINGS_MODEL2_B_TARIFF.keys())

DEFAULT_HORIZON_YEARS = 20

# Estrategias de carga soportadas actualmente por el motor de cálculo.
SUPPORTED_SURPLUS_STRATEGIES = {"PV surplus first", "Best price PV vs Grid"}

def project_savings(savings_y1, tariff, container_type, pct_charge_pv=None, years=None):

    if years is None:
        years = range(1, DEFAULT_HORIZON_YEARS+1)

    container = "Risen" if "risen" in container_type.lower() else "Solax"

    use_model2 = (pct_charge_pv is not None and tariff in SAVINGS_MODEL2_VALID_TARIFFS and SAVINGS_MODEL2_PCT_CHARGE_PV_MIN <= pct_charge_pv <= SAVINGS_MODEL2_PCT_CHARGE_PV_MAX)

    years_list = list(years)
    ratios = []

    if use_model2:
        b_tariff = SAVINGS_MODEL2_B_TARIFF[tariff]
        b_container = SAVINGS_MODEL2_B_CONTAINER_SOLAX if container == "Solax" else 0.0
        for year in years_list:
            if year == 1:
                ratios.append(1.0)
                continue
            ratio = (SAVINGS_MODEL2_INTERCEPT + SAVINGS_MODEL2_B_YEAR*year + SAVINGS_MODEL2_B_YEAR2*year**2 + b_tariff*year + b_container*year + SAVINGS_MODEL2_B_PCT_CHARGE_PV*pct_charge_pv*year)
            ratios.append(ratio)
    else:
        b_tariff = SAVINGS_MODEL_B_TARIFF.get(tariff, 0.0)
        b_container = SAVINGS_MODEL_B_CONTAINER_SOLAX if container == "Solax" else 0.0
        for year in years_list:
            if year == 1:
                ratios.append(1.0)
                continue
            ratio = (SAVINGS_MODEL_INTERCEPT + SAVINGS_MODEL_B_YEAR*year + SAVINGS_MODEL_B_YEAR2*year**2 + b_tariff*year + b_container*year)
            ratios.append(ratio)

    return pd.Series(np.array(ratios)*savings_y1, index=years_list, name="SAVINGS_estimado")

def _pv_degradation_factor(year):
    if year in PV_DEGRADATION_CURVE:
        return PV_DEGRADATION_CURVE[year]
    last_year = max(PV_DEGRADATION_CURVE)

    return PV_DEGRADATION_CURVE[last_year] - _PV_DEGRADATION_SLOPE*(year-last_year)


def project_ppa_savings(ppa_imp, mwh_pv_sc_y1, years=None):

    if years is None:
        years = range(1, DEFAULT_HORIZON_YEARS+1)

    years_list = list(years)
    savings = [ppa_imp*mwh_pv_sc_y1*_pv_degradation_factor(year) for year in years_list]

    return pd.Series(savings, index=years_list, name="SAVINGS_PPA")

def read_cups_info(file, sheet_name="CUPS"):
    """
    Lee la configuración de CUPS: Tariff/Client/Plant son valores únicos para
    todo el workbook (no varían por escenario ni por periodo), a diferencia de
    'ContPower (MW)' que sí varía por periodo tarifario (P1-P6).
    """

    df = pd.read_excel(file, sheet_name=sheet_name, header=0)

    return {
        "Tariff"    :   df["Tariff"].dropna().iloc[0],
        "Client"    :   df["Client"].dropna().iloc[0],
        "Plant"     :   df["Plant"].dropna().iloc[0],
    }


def load_scenarios(file, sheet_name="Scenarios"):

    df = pd.read_excel(file, sheet_name=sheet_name, header=0)
    df = df.dropna(subset=["Scenario - Num"]).copy()

    if df.empty:
        raise ValueError(f"'{sheet_name}' has no defined scenarios")

    tariff = read_cups_info(file)["Tariff"]  # Tariff vive en CUPS, no por escenario

    scenarios = []
    for _, row in df.iterrows():
        container_type = row["Type of Container"]
        provider = "Solax" if "solax" in str(container_type).lower() else "Risen"

        strategy = str(row["Surplus Strategy"]).strip()
        if strategy not in SUPPORTED_SURPLUS_STRATEGIES:
            raise NotImplementedError(
                f"Scenario '{row["Scenario"]}': Surplus Strategy='{strategy}' can't be run"
                f"please choose one of the following strategies: {sorted(SUPPORTED_SURPLUS_STRATEGIES)}."
            )

        ppa_imp = float(row["PV PPA Price for charging €/MWh"]) - float(row["Original PPA price €/MWh"])
        scenarios.append({
            "Scenario"          :   row["Scenario"],
            "Container Type"    :   container_type,
            "Provider"          :   provider,
            "Nominal Capacity"  :   float(row["Nominal Capacity"]),
            "N Containers"      :   float(row["N containers"]),
            "C-Factor"          :   float(row["C-Factor"]),
            "Tariff"            :   tariff,
            "PPA Mode"          :   row["Price mode from PV surplus"],
            "Surplus Strategy"  :   strategy,
            "PPA Price"         :   float(row["PV PPA Price for charging €/MWh"]),
            "PPA Improvement"   :   ppa_imp,
            "Discharge Cost"    :   float(row["Discharge Cost"]) if "Discharge Cost" in row and pd.notna(row.get("Discharge Cost")) else 0.0,
            "Cycles/Day"        :   float(row["Cycles/day"]),
            "tolls"             :   0, #-----------------------------------------------------------------------------------------TO-DO (WIP)
            "€ Leasing Monthly" :   float(row["€ Leasing Monthly"]),
        })

    return scenarios

def solve_scenario(data_base, scenario):
    """
    Resuelve el MILP de un único escenario (selección de curva de degradación
    por proveedor + branching de estrategia) y devuelve (model, results, inputs).

    No calcula KPIs ni proyecciones de ahorro: eso es responsabilidad de quien
    consume el resultado (_solve_combo para el sweep, un dashboard para
    visualización).
    """

    inputs = {
        "Pot BESS"          :   scenario["Nominal Capacity"],
        "N containers"      :   scenario["N Containers"],
        "C-factor"          :   scenario["C-Factor"],
        "TARIFF"            :   scenario["Tariff"],
        "PPA Mode"          :   scenario["PPA Mode"],
        "PPA Price"         :   scenario["PPA Price"],
        "Discharge Cost"    :   scenario["Discharge Cost"],
        "Cycles/Day"        :   scenario["Cycles/Day"],
        "tolls"             :   scenario["tolls"],
    }

    data = data_base.copy()
    if scenario["Provider"] == "Solax":
        data["BESS Degradation factor"] = data["BESS Degradation factor - Solax"]
    else:
        data["BESS Degradation factor"] = data["BESS Degradation factor - Risen"]

    if scenario["Surplus Strategy"] == "PV surplus first":
        model, results = pv_first_daily.opt_pv_first_daily(data, inputs)
    elif scenario["Surplus Strategy"] == "Best price PV vs Grid":
        model, results = best_price_daily.opt_best_price_daily(data, inputs)
    else:
        raise NotImplementedError(
            f"Scenario '{scenario["Scenario"]}': Surplus Strategy='{scenario["Surplus Strategy"]}' can't be run"
            f"please choose one of the following strategies: {sorted(SUPPORTED_SURPLUS_STRATEGIES)}."
        )

    return model, results, inputs


def _solve_scenario_raw(data_base, scenario):
    model, results, inputs = solve_scenario(data_base, scenario)
    return scenario["Scenario"], results, inputs, scenario


def solve_all_scenarios(file, only=None, n_workers=None, parallel=True):
    """
    Resuelve (en paralelo por defecto) todos los escenarios definidos en 'file',
    o solo los indicados en 'only' (lista de nombres de Scenario), y devuelve un
    dict {scenario_name: {"results": DataFrame horario, "inputs": dict, "scenario": dict}}.

    Pensado para alimentar un dashboard de visualización que no necesita
    recalcular KPIs/proyecciones de ahorro, solo los resultados horarios crudos.
    """

    scenarios = load_scenarios(file)
    if only is not None:
        scenarios = [s for s in scenarios if s["Scenario"] in set(only)]

    data_base = pd.read_excel(file, sheet_name="Hourly Data", header=2)

    if not parallel:
        raw = [_solve_scenario_raw(data_base, scen) for scen in scenarios]
    else:
        workers = n_workers or max(os.cpu_count() - 1, 1)
        raw = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_solve_scenario_raw, data_base, scen): scen["Scenario"] for scen in scenarios}
            for future in as_completed(futures):
                raw.append(future.result())

    return {
        name: {"results": results, "inputs": inputs, "scenario": scenario}
        for name, results, inputs, scenario in raw
    }


def _solve_combo(
        data_base,
        scenario,
        horizon_years,
        savings_threshold
):

    container_type = scenario["Container Type"]
    nominal_capacity = scenario["Nominal Capacity"]
    n_containers = scenario["N Containers"]
    bess_capacity = nominal_capacity*n_containers
    ppa_imp = scenario["PPA Improvement"]

    print(f"Solving: [{scenario["Scenario"]}]: {container_type} x {n_containers} = {bess_capacity:.3f} MWh")

    model, results, inputs = solve_scenario(data_base, scenario)
    calc_data = aux_functions.calculate_table(results, inputs["PPA Price"], inputs)
    savings_y1 = calc_data["€ Savings from BESS"]

    mwh_pv_direct_sc = calc_data["MWh PV Direct SC"]
    proyeccion_ppa = project_ppa_savings(ppa_imp, mwh_pv_sc_y1=mwh_pv_direct_sc, years=range(1, horizon_years+1))
    savings_ppa_annual = abs(proyeccion_ppa.iloc[0])
    savings_ppa_n_years = abs(proyeccion_ppa.sum())

    pct_charge_pv = calc_data["% Charge from PV"]
    if pct_charge_pv is not None:
        pct_charge_pv = pct_charge_pv/100.0

    mwh_charge_pv = calc_data["MWh Charge from PV"]
    mwh_surplus_pv = (data["PV Generation kWh"] - data["AC kWh"])/1000
    perc_surplus_to_BESS = (mwh_charge_pv/(mwh_surplus_pv.sum()))*100
    perc_pv_ac_bess = ((data["AC kWh"].sum()/1000 + mwh_charge_pv)/(data["PV Generation kWh"].sum()/1000) - (data["AC kWh"].sum()/1000)/(data["PV Generation kWh"].sum()/1000))*100

    proyeccion = project_savings(savings_y1=savings_y1, tariff=inputs["TARIFF"], container_type=container_type, pct_charge_pv=pct_charge_pv, years=range(1, horizon_years+1),)
    savings_bess_n_years = proyeccion.sum()
    savings_total_n_years = savings_bess_n_years + savings_ppa_n_years

    annual_leasing_cost = scenario["€ Leasing Monthly"]*n_containers*12
    leasing_total_n_years = annual_leasing_cost*horizon_years

    savings_pct = ((savings_total_n_years - leasing_total_n_years) / leasing_total_n_years)*100

    return {
        "Scenario"                                          :   scenario["Scenario"],
        "Container Type"                                    :   container_type,
        "N Containers"                                      :   n_containers,
        "Nominal Capacity"                                  :   nominal_capacity,
        "BESS Capacity (MWh)"                               :   bess_capacity,
        "% Charge from PV"                                  :   pct_charge_pv*100,
        "MWh Charge from PV"                                :   mwh_charge_pv,
        "% PV Surplus to BESS"                              :   perc_surplus_to_BESS,
        "Δ% PV Self-consumption"                            :   perc_pv_ac_bess,
        "€ Savings from PPA improvement"                    :   savings_ppa_annual,
        f"€ Savings from PPA improvement {horizon_years}y"  :   savings_ppa_n_years,
        "€ Savings BESS y1"                                 :   savings_y1,
        f"€ Savings from BESS {horizon_years}y"             :   savings_bess_n_years,
        "€ Total Savings y1"                                :   savings_y1 + savings_ppa_annual,
        f"€ Total Savings {horizon_years}y"                 :   savings_total_n_years,
        "€ Annual Leasing"                                  :   annual_leasing_cost,
        f"€ Leasing {horizon_years}y"                       :   leasing_total_n_years,
        "% Savings vs Leasing"                              :   savings_pct,
        "(>%.0f%%)" % savings_threshold                     :   savings_pct > savings_threshold,
    }
    

def sweep_bess_sizes(
        file,
        horizon_years = DEFAULT_HORIZON_YEARS,
        savings_threshold = 20.0,
        n_workers = None,
        parallel = True,
):
    
    scenarios = load_scenarios(file)
    data_base = pd.read_excel(file, sheet_name="Hourly Data", header=2)

    if not parallel:
        total_results = [_solve_combo(data_base, scen, horizon_years, savings_threshold) for scen in scenarios]
    else:
        workers = n_workers or max(os.cpu_count() - 1, 1)
        total_results = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_solve_combo, data_base, scen, horizon_years, savings_threshold): scen["Scenario"] for scen in scenarios}
            for future in as_completed(futures):
                total_results.append(future.result())

    df_results = pd.DataFrame(total_results)
    df_results = df_results.sort_values("BESS Capacity (MWh)").reset_index(drop=True)
    return highlight_results(df_results)

def highlight_results(df_results):

    def _highlight_row(row):
        threshold_cols = [c for c in row.index if c.startswith("(>")]
        if threshold_cols and row[threshold_cols[0]]:
            return ["background-color : #3B7D23"]*len(row)
        return [""]*len(row)
    
    money_cols = [c for c in df_results.columns if c.startswith("€")]

    return(df_results.style.apply(_highlight_row, axis=1).format({c: "{:,.0f} €" for c in money_cols}).format({"% Savings vs Leasing": "{:.1f}%"}))



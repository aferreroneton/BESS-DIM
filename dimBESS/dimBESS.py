import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np
import pv_first_daily
import best_price_daily
import aux_functions
import mwh_extension

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

DEFAULT_HORIZON_YEARS = 15

# Estrategias de carga soportadas actualmente por el motor de cálculo.
SUPPORTED_SURPLUS_STRATEGIES = {"PV surplus first", "Best price PV vs Grid"}

# "Base study": proyección de savings vía el modelo de regresión externo (58 simulaciones
# históricas de otra herramienta), dimensionando solo en el año 1 (project_savings).
# "Extended study": resuelve el MILP en año 1, 10 y 20 para el escenario concreto y ajusta
# una curva propia (parábola exacta por los 3 puntos) en vez de usar el modelo externo.
SUPPORTED_STUDY_TYPES = {"Base study", "Extended study"}
EXTENDED_STUDY_YEARS = (1, 10, 20)

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


def project_savings_extended(savings_y1, savings_y10, savings_y20, years=None):
    """
    Contraparte de project_savings() para "Extended study": en vez de aplicar el modelo de
    regresión calibrado externamente sobre 58 simulaciones históricas, ajusta una parábola
    exacta (2º grado, 3 puntos -> 3 incógnitas) por los ratios simulados en año 1/10/20 del
    propio escenario, y la extrapola al resto de años del horizonte.
    """

    if years is None:
        years = range(1, DEFAULT_HORIZON_YEARS+1)

    years_list = list(years)

    ratio_10 = savings_y10/savings_y1 if savings_y1 else 0.0
    ratio_20 = savings_y20/savings_y1 if savings_y1 else 0.0

    coeffs = np.polyfit(EXTENDED_STUDY_YEARS, [1.0, ratio_10, ratio_20], 2)
    poly = np.poly1d(coeffs)

    ratios = np.array([poly(year) for year in years_list])

    return pd.Series(ratios*savings_y1, index=years_list, name="SAVINGS_estimado")

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

def load_hourly_data(file, sheet_name="Hourly Data"):
    """
    Lee la hoja de datos horarios y descarta filas de cola sin 'Date&Time' válido.

    Excels reales han aparecido con decenas de filas de basura al final (fórmulas
    arrastradas más allá del rango real de fechas): 'Power demand kWh' seguía
    arrastrando una fórmula en esas filas mientras el resto de columnas quedaban en
    blanco, colando NaN en el MILP (p.ej. 'PV Generation kWh') y reventando con un
    error interno de Pyomo/CBC en vez de un aviso claro.
    """

    data = pd.read_excel(file, sheet_name=sheet_name, header=2)
    valid_mask = data["Date&Time"].notna()
    if not valid_mask.all():
        n_dropped = int((~valid_mask).sum())
        print(f"WARNING: descartadas {n_dropped} fila(s) de cola en '{sheet_name}' sin 'Date&Time' válido.")
    return data[valid_mask].reset_index(drop=True)


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


def read_cont_power_by_period(file, sheet_name="CUPS"):
    """Period -> ContPower (MW), la misma tabla que usa el año 1 (CUPS!A2:A7 / B2:B7)."""

    df = pd.read_excel(file, sheet_name=sheet_name, header=0)

    return df.set_index("Period")["ContPower (MW)"].to_dict()


def load_extension_data(file, tariff):
    """
    Carga las hojas adicionales del mismo Excel de entradas que necesita mwh_extension
    para proyectar demanda/generación/precios/degradación a un año de operación futuro
    (10, 20, ...). Se lee una vez por archivo/tarifa y se reutiliza para todos los
    escenarios de "Extended study" (periodos/precios/curvas no dependen del escenario).
    """

    periods = pd.read_excel(file, sheet_name="Periodos tarifarios", skiprows=2, nrows=13, usecols="B:Z")
    periods.columns = ["Month"] + list(range(1, 25))

    prices_total = pd.read_excel(file, sheet_name="Aurora2026Q1_AllTariffs_FinalPr")
    prices = prices_total[prices_total["Tariff"] == tariff][
        ["Date&Time", "Pool price", "Total Grid Costs", "Final Prices", "Tolls and RC"]
    ]

    curves_risen = pd.read_excel(file, sheet_name="DefEff Curves - Risen", header=2, nrows=21, usecols="A:J")
    curves_solax = pd.read_excel(file, sheet_name="DefEff Curves - Solax", header=2, nrows=21, usecols="A:J")

    return {
        "periods"               :   periods,
        "prices"                :   prices,
        "curves_risen"          :   curves_risen,
        "curves_solax"          :   curves_solax,
        "cont_power_by_period"  :   read_cont_power_by_period(file),
    }


def project_year_data(data_base, extension_data, y1, years):
    """
    Proyecta data_base (Hourly Data del año 1) a los años de operación indicados vía
    mwh_extension, y adjunta 'Cont Power MW' (ausente en la salida de mwh_extension) con
    el mismo lookup Period -> ContPower(MW) de CUPS usado en el año 1, asumiendo que los
    términos del contrato de potencia no cambian a lo largo del horizonte.
    """

    data_by_year = mwh_extension.mwh_extension(
        data_base,
        extension_data["periods"],
        extension_data["prices"],
        extension_data["curves_risen"],
        extension_data["curves_solax"],
        y1,
        years,
    )

    for data_year in data_by_year.values():
        data_year["Cont Power MW"] = data_year["Period"].map(extension_data["cont_power_by_period"])

    return data_by_year


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

        study_type = str(row["Study Type"]).strip() if "Study Type" in row and pd.notna(row.get("Study Type")) else "Base study"
        if study_type not in SUPPORTED_STUDY_TYPES:
            raise NotImplementedError(
                f"Scenario '{row["Scenario"]}': Study Type='{study_type}' desconocido, "
                f"debe ser uno de: {sorted(SUPPORTED_STUDY_TYPES)}."
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
            "Study Type"        :   study_type,
        })

    return scenarios

def _validate_hourly_data(data, scenario):
    """
    Comprueba que las columnas horarias que van a alimentar el MILP no tengan huecos
    (NaN). Sin esto, un solo valor vacío en el Excel de entradas produce un cota
    'nan' en una constraint de Pyomo y revienta con un traceback de CBC/LP-writer
    ilegible para quien no conoce el código; aquí se señala la columna y las fechas
    concretas para poder arreglarlo en el Excel.
    """

    required_cols = [
        "Power demand kWh", "PV Generation kWh", "Cont Power MW", "Final Prices",
        "BESS Degradation factor", "RTE Efficiency",
    ]
    if scenario["PPA Mode"] == "Merch compensation":
        required_cols.append("Pool price")
    if scenario["tolls"] == 0:
        required_cols.append("Tolls and RC")

    problems = []
    for col in required_cols:
        if col not in data.columns:
            problems.append(f"falta la columna '{col}'")
            continue
        bad_mask = data[col].isna()
        if bad_mask.any():
            if "Date&Time" in data.columns:
                bad_values = data.loc[bad_mask, "Date&Time"].astype(str).tolist()
            else:
                bad_values = data.index[bad_mask].tolist()
            problems.append(f"'{col}' tiene {int(bad_mask.sum())} valor(es) vacío(s)/NaN, ej.: {bad_values[:5]}")

    if problems:
        raise ValueError(
            f"Scenario '{scenario["Scenario"]}': datos horarios inválidos antes de resolver el MILP:\n- "
            + "\n- ".join(problems)
        )


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

    _validate_hourly_data(data, scenario)

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


def _solve_scenario_year_savings(data_year, scenario):
    """Resuelve el MILP con los datos proyectados de un año de operación futuro y
    devuelve únicamente el '€ Savings from BESS' de ese año (para Extended study)."""

    _, results_year, inputs_year = solve_scenario(data_year, scenario)
    calc_year = aux_functions.calculate_table(results_year, inputs_year["PPA Price"], inputs_year)
    return calc_year["€ Savings from BESS"]


def kpi_row_from_results(data_base, scenario, results, inputs, horizon_years, savings_threshold, extension_data=None, y1=None):
    """
    Calcula KPIs y proyección de ahorro a partir de un año 1 YA resuelto: no vuelve a
    llamar a solve_scenario, para que tanto el sweep en paralelo (solve_and_analyze_scenarios)
    como una resolución interactiva suelta (Scenario Builder) puedan reutilizar el mismo
    resultado de año 1 sin resolver el MILP dos veces.

    Para "Extended study" sí resuelve el MILP dos veces más (año 10 y año 20 proyectados
    vía mwh_extension), porque esos años no se calculan en ningún otro sitio.
    """

    data = data_base.copy()

    container_type = scenario["Container Type"]
    nominal_capacity = scenario["Nominal Capacity"]
    n_containers = scenario["N Containers"]
    bess_capacity = nominal_capacity*n_containers
    ppa_imp = scenario["PPA Improvement"]
    study_type = scenario.get("Study Type", "Base study")

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

    savings_y10 = np.nan
    savings_y20 = np.nan
    if study_type == "Extended study":
        if extension_data is None or y1 is None:
            raise ValueError(
                f"Scenario '{scenario["Scenario"]}': Study Type='Extended study' requiere "
                f"extension_data/y1 (ver load_extension_data / sweep_bess_sizes)."
            )
        data_by_year = project_year_data(data_base, extension_data, y1, years=[10, 20])
        savings_y10 = _solve_scenario_year_savings(data_by_year[10], scenario)
        savings_y20 = _solve_scenario_year_savings(data_by_year[20], scenario)

        proyeccion = project_savings_extended(savings_y1=savings_y1, savings_y10=savings_y10, savings_y20=savings_y20, years=range(1, horizon_years+1))
    else:
        proyeccion = project_savings(savings_y1=savings_y1, tariff=inputs["TARIFF"], container_type=container_type, pct_charge_pv=pct_charge_pv, years=range(1, horizon_years+1),)

    savings_bess_n_years = proyeccion.sum()
    savings_total_n_years = savings_bess_n_years + savings_ppa_n_years

    annual_leasing_cost = scenario["€ Leasing Monthly"]*n_containers*12
    if horizon_years > 15:
        leasing_total_n_years = annual_leasing_cost*15
    else:
        leasing_total_n_years = annual_leasing_cost*horizon_years

    savings_pct = ((savings_total_n_years - leasing_total_n_years) / leasing_total_n_years)*100

    return {
        "Scenario"                                          :   scenario["Scenario"],
        "Client"                                            :   client_from_scenario_name(scenario["Scenario"]),
        "Study Type"                                        :   study_type,
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
        "€ Savings BESS y10 (simulado)"                     :   savings_y10,
        "€ Savings BESS y20 (simulado)"                     :   savings_y20,
        f"€ Savings from BESS {horizon_years}y"             :   savings_bess_n_years,
        "€ Total Savings y1"                                :   savings_y1 + savings_ppa_annual,
        f"€ Total Savings {horizon_years}y"                 :   savings_total_n_years,
        "€ Annual Leasing"                                  :   annual_leasing_cost,
        f"€ Leasing {horizon_years}y"                       :   leasing_total_n_years,
        "% Savings vs Leasing"                              :   savings_pct,
        "(>%.0f%%)" % savings_threshold                     :   savings_pct > savings_threshold,
    }
    

def _solve_scenario_combined(data_base, scenario, horizon_years, savings_threshold, extension_data=None, y1=None):
    """
    Resuelve el año 1 UNA sola vez y devuelve tanto los resultados horarios crudos (para
    las páginas de visualización del dashboard) como la fila de KPIs/proyección de ahorro
    (para Scenario Results), evitando resolver el mismo escenario dos veces.
    """

    print(f"Solving: [{scenario["Scenario"]}]: {scenario["Container Type"]} x {scenario["N Containers"]} "
          f"= {scenario["Nominal Capacity"]*scenario["N Containers"]:.3f} MWh ({scenario.get("Study Type", "Base study")})")

    model, results, inputs = solve_scenario(data_base, scenario)
    kpi_row = kpi_row_from_results(data_base, scenario, results, inputs, horizon_years, savings_threshold, extension_data, y1)

    return scenario["Scenario"], results, inputs, scenario, kpi_row


def solve_and_analyze_scenarios(
        file,
        only=None,
        n_workers=None,
        parallel=True,
        horizon_years=DEFAULT_HORIZON_YEARS,
        savings_threshold=20.0,
):
    """
    Resuelve (en paralelo por defecto) los escenarios de 'file' (todos, o solo los
    indicados en 'only') UNA sola vez cada uno, devolviendo:
      - scenario_results: {name: {"results":, "inputs":, "scenario":}}, para las páginas
        de visualización (año 1).
      - kpi_rows: {name: dict}, con los KPIs/proyección de ahorro (para Scenario Results,
        vía build_results_table).

    Pensado para el botón único "Run Scenarios" del dashboard: antes había un solve por
    separado para visualización (solve_all_scenarios) y otro para el sweep de KPIs
    (sweep_bess_sizes), resolviendo el mismo año 1 dos veces.
    """

    scenarios = load_scenarios(file)
    if only is not None:
        scenarios = [s for s in scenarios if s["Scenario"] in set(only)]

    data_base = load_hourly_data(file)

    extension_data = None
    y1 = None
    if any(scen.get("Study Type", "Base study") == "Extended study" for scen in scenarios):
        tariff = read_cups_info(file)["Tariff"]
        extension_data = load_extension_data(file, tariff)
        y1 = int(data_base["Year"].dropna().iloc[0])

    if not parallel:
        raw = [_solve_scenario_combined(data_base, scen, horizon_years, savings_threshold, extension_data, y1) for scen in scenarios]
    else:
        workers = n_workers or max(os.cpu_count() - 1, 1)
        raw = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_solve_scenario_combined, data_base, scen, horizon_years, savings_threshold, extension_data, y1): scen["Scenario"]
                for scen in scenarios
            }
            for future in as_completed(futures):
                raw.append(future.result())

    scenario_results = {name: {"results": results, "inputs": inputs, "scenario": scenario} for name, results, inputs, scenario, kpi_row in raw}
    kpi_rows = {name: kpi_row for name, results, inputs, scenario, kpi_row in raw}

    return scenario_results, kpi_rows


def client_from_scenario_name(name):
    """
    Agrupador "Cliente" para Scenario Results: todo lo que va antes del segundo '_' del
    nombre de escenario (Client_Plant_ContainerType_NContainer_SizeMWh_PriceMode), es
    decir Client_Plant combinados -- el sitio/CUPS que generó ese escenario.
    """

    parts = str(name).split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else str(name)


def build_results_table(kpi_rows):
    """Convierte un dict {name: kpi_row} (de solve_and_analyze_scenarios / kpi_row_from_results)
    en la tabla estilizada y resaltada que consume la página Scenario Results."""

    df_results = pd.DataFrame(list(kpi_rows.values()))
    if df_results.empty:
        return df_results

    df_results = df_results.sort_values("BESS Capacity (MWh)").reset_index(drop=True)
    return highlight_results(df_results)


def sweep_bess_sizes(
        file,
        horizon_years = DEFAULT_HORIZON_YEARS,
        savings_threshold = 20.0,
        n_workers = None,
        parallel = True,
):
    """Entrypoint standalone (notebook/CLI): resuelve todos los escenarios y devuelve
    directamente la tabla estilizada. El dashboard usa solve_and_analyze_scenarios +
    build_results_table por separado, para no resolver el año 1 dos veces."""

    _, kpi_rows = solve_and_analyze_scenarios(
        file, n_workers=n_workers, parallel=parallel, horizon_years=horizon_years, savings_threshold=savings_threshold
    )
    return build_results_table(kpi_rows)

def highlight_results(df_results):

    def _highlight_row(row):
        threshold_cols = [c for c in row.index if c.startswith("(>")]
        if threshold_cols and row[threshold_cols[0]]:
            # Cyan corporativo (theme.CYAN_TINT en el dashboard): "apto" no debe leerse
            # como alerta, por eso no se usa el coral/rojo reservado para resultados destacados.
            return ["background-color : #E1F5F9"]*len(row)
        return [""]*len(row)
    
    # OJO: dos llamadas encadenadas a .format() sin 'subset' se pisan entre sí (pandas
    # resetea a formato por defecto las columnas no incluidas en la última llamada), por
    # eso van todas las columnas en un único dict/llamada.
    money_cols = [c for c in df_results.columns if c.startswith("€")]
    formatters = {c: "{:,.0f} €" for c in money_cols}
    formatters["% Savings vs Leasing"] = "{:.1f}%"

    return(df_results.style.apply(_highlight_row, axis=1).format(formatters, na_rep="–"))



import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np
import pv_first_daily
import best_price_daily
import pbi_logic_daily
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

# Ratio mediano real (SAVINGS año n / SAVINGS año 1) del grupo de referencia (6.1TD +
# Risen, 19 simulaciones multi-año) del histórico de 58 simulaciones (co_exec) que
# calibró el modelo de regresión externo -- fuente: "Savings BESS Evo.pbix", tabla
# simHist. La regresión cuadrática (SAVINGS_MODEL_*) alisaba por completo un patrón real
# y consistente (100% de las 49 simulaciones multi-año lo muestran): un valle en año 4 y
# un repunte en año 5-6 antes de retomar la caída, ligado al spread real de precios, no
# a un artefacto de un cliente concreto. Sustituye a "Intercept + b_year*year +
# b_year2*year²" como forma base de project_savings(); los ajustes de tarifa/container
# (y % Charge from PV en el Modelo 2) se mantienen como antes, sumados sobre esta forma.
SAVINGS_EMPIRICAL_SHAPE_RATIO = {
    1   :   1.000000,
    2   :   0.943715,
    3   :   0.928600,
    4   :   0.882018,
    5   :   0.910505,
    6   :   0.923412,
    7   :   0.895400,
    8   :   0.833068,
    9   :   0.823462,
    10  :   0.813977,
    11  :   0.805995,
    12  :   0.804965,
    13  :   0.776808,
    14  :   0.754562,
    15  :   0.714622,
    16  :   0.689830,
    17  :   0.660010,
    18  :   0.627080,
    19  :   0.597566,
    20  :   0.577189,
}


def _empirical_savings_shape_ratio(year):
    if year in SAVINGS_EMPIRICAL_SHAPE_RATIO:
        return SAVINGS_EMPIRICAL_SHAPE_RATIO[year]

    last_year = max(SAVINGS_EMPIRICAL_SHAPE_RATIO)
    slope = SAVINGS_EMPIRICAL_SHAPE_RATIO[last_year] - SAVINGS_EMPIRICAL_SHAPE_RATIO[last_year - 1]

    return SAVINGS_EMPIRICAL_SHAPE_RATIO[last_year] + slope*(year - last_year)


DEFAULT_HORIZON_YEARS = 15

# Estrategias de carga soportadas actualmente por el motor de cálculo.
SUPPORTED_SURPLUS_STRATEGIES = {"PV surplus first", "Best price PV vs Grid", "Solve (PBI logic)"}

# "Base study": proyección de savings vía el modelo de regresión externo (58 simulaciones
# históricas de otra herramienta), dimensionando solo en el año 1 (project_savings).
# "Extended study": resuelve el MILP en los años de EXTENDED_STUDY_YEARS para el escenario
# concreto y ajusta una curva propia (polinomio exacto por esos N puntos) en vez de usar el
# modelo externo.
#
# Antes eran año 1/10/20: el histórico (simHist) y la simulación año-a-año muestran un
# valle en año 4 y un repunte en año 5-6 antes de que la caída se acelere en año 7-8 -- con
# 1/10/20 esa dinámica se saltaba por completo (de año 1 se pasaba a año 10).
#
# Búsqueda exhaustiva sobre 11 años reales resueltos (escenario Harinera 15,05MWh, ver
# informe de metodología) entre todas las combinaciones de calibración razonables:
#   1-10-20 (anterior)      MAE 1,27%  -- se salta el valle/repunte por completo
#   1-5-8   (3 puntos)      MAE 1,16%  -- mejor en años <=10 (0,74%) pero peor en años >10
#                                         (2,43%; pierde el ancla de largo plazo)
#   1-9-20  (mejor de 3)    MAE 0,95%
#   1-6-9-15 (elegido)      MAE 0,59%  -- año 6 (pico real), año 9 (tras el repunte), año 15
#                                         (horizonte por defecto de la herramienta, ver
#                                         DEFAULT_HORIZON_YEARS); extrapola a año 20 con solo
#                                         -0,45% de error pese a no anclar ahí
#   1-7-15-20 (mejor de 4)  MAE 0,54%  -- marginalmente mejor pero exige resolver año 20
#                                         (previsión a más distancia) sin ganancia relevante
# Anclar exactamente en el pico (probado con año 6 como único punto intermedio, sin año 9)
# da un ajuste inestable que se dispara en la extrapolación (-31,8% en año 20) -- por eso
# hace falta un 4º punto que sujete la cola.
SUPPORTED_STUDY_TYPES = {"Base study", "Extended study"}
EXTENDED_STUDY_YEARS = (1, 6, 9, 15)

def project_savings(savings_y1, tariff, container_type, pct_charge_pv=None, years=None):
    """
    "Base study": ratio(año) = forma empírica real (SAVINGS_EMPIRICAL_SHAPE_RATIO, grupo
    de referencia 6.1TD+Risen) + ajuste de tarifa/container (y de % Charge from PV en el
    Modelo 2), igual que antes. Antes la "forma" era la parábola ajustada por regresión
    (Intercept + b_year·año + b_year²·año²), que alisaba el valle/repunte real de año
    4-6; ahora se parte directamente de la mediana histórica real y se le suma el mismo
    ajuste de tarifa/container ya calibrado (año 1 sigue fijado a 1.0 exacto).
    """

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
            ratio = (_empirical_savings_shape_ratio(year) + b_tariff*year + b_container*year + SAVINGS_MODEL2_B_PCT_CHARGE_PV*pct_charge_pv*year)
            ratios.append(ratio)
    else:
        b_tariff = SAVINGS_MODEL_B_TARIFF.get(tariff, 0.0)
        b_container = SAVINGS_MODEL_B_CONTAINER_SOLAX if container == "Solax" else 0.0
        for year in years_list:
            if year == 1:
                ratios.append(1.0)
                continue
            ratio = (_empirical_savings_shape_ratio(year) + b_tariff*year + b_container*year)
            ratios.append(ratio)

    return pd.Series(np.array(ratios)*savings_y1, index=years_list, name="SAVINGS_estimado")


def _annual_degradation_factors(provider, extension_data, years):
    """BESS Degradation por año de operación (directo de la curva del fabricante, sin
    interpolar dentro del año -- aquí basta una cifra por año)."""

    curves = extension_data["curves_risen"] if provider == "Risen" else extension_data["curves_solax"]
    deg_lookup = curves.set_index("Operation year")["BESS Degradation"].to_dict()

    return {year: deg_lookup.get(year, np.nan) for year in years}


def _annual_price_spread(extension_data, y1, years):
    """
    Spread diario medio (máximo - mínimo de 'Final Prices' cada día, promediado en el
    año natural correspondiente) para cada año de operación, a partir del forecast de
    precios real (Aurora) ya cargado en extension_data -- sin resolver el MILP.
    """

    prices = extension_data["prices"][["Date&Time", "Final Prices"]].copy()
    prices["Date&Time"] = pd.to_datetime(prices["Date&Time"])
    prices["Calendar Year"] = prices["Date&Time"].dt.year
    prices["Date"] = prices["Date&Time"].dt.date

    daily = prices.groupby(["Calendar Year", "Date"])["Final Prices"].agg(["max", "min"])
    daily_spread_by_calendar_year = (daily["max"] - daily["min"]).groupby("Calendar Year").mean()

    return {year: daily_spread_by_calendar_year.get(y1 + (year - 1), np.nan) for year in years}


def project_savings_extended(savings_y1, savings_by_calib_year, provider, extension_data, y1, years=None):
    """
    Contraparte de project_savings() para "Extended study". El spread diario real de
    precios (Aurora) combinado con la degradación de batería ("raw_shape") ya reproduce
    bastante bien el valle de año 4 y el repunte de año 5-6 vistos tanto en el histórico
    (simHist) como en la simulación año-a-año real -- pero un polinomio puro por puntos muy
    separados (año 1/10/20, versión original) se saltaba esa dinámica por completo. En su
    lugar:

    1) raw_shape(año) = degradación_batería(año) x spread_diario_real(año), normalizado
       a año 1 -- perfil "físico" año a año con la forma real del mercado.
    2) corrección(año): polinomio de grado len(EXTENDED_STUDY_YEARS)-1 por los puntos de
       EXTENDED_STUDY_YEARS tal que raw_shape, multiplicado por ella, reproduzca EXACTAMENTE
       los ratios realmente simulados en esos años (año 1 -> 1.0 por construcción).
    3) ratio final(año) = raw_shape(año) x corrección(año): calibrado con los puntos
       simulados, pero con la forma entre/más allá de ellos gobernada por el spread real.

    savings_by_calib_year: dict {año: savings_del_MILP} para cada año de
    EXTENDED_STUDY_YEARS distinto de 1 (p.ej. {6: savings_y6, 9: savings_y9, 15: savings_y15}).

    Número de puntos de calibración (ver informe de metodología para la búsqueda completa):
    más puntos = mejor ajuste pero más resoluciones del MILP por escenario ("Extended
    study" tarda ~len(EXTENDED_STUDY_YEARS)x lo que "Base study"). Anclar justo en un pico
    real (año 6) con solo 2 puntos más es inestable en la extrapolación -- hace falta un
    punto adicional que sujete la cola (por eso son 4 puntos y no 3).
    """

    if years is None:
        years = range(1, DEFAULT_HORIZON_YEARS+1)

    years_list = list(years)
    all_years = sorted(set(years_list) | set(EXTENDED_STUDY_YEARS))

    deg = _annual_degradation_factors(provider, extension_data, all_years)
    spread = _annual_price_spread(extension_data, y1, all_years)
    raw = {year: deg[year]*spread[year] for year in all_years}
    raw_ratio = {year: raw[year]/raw[1] for year in all_years}

    true_ratio = {1: 1.0}
    for year, savings_year in savings_by_calib_year.items():
        true_ratio[year] = savings_year/savings_y1 if savings_y1 else 0.0

    correction_points = [true_ratio[y]/raw_ratio[y] for y in EXTENDED_STUDY_YEARS]
    coeffs = np.polyfit(EXTENDED_STUDY_YEARS, correction_points, len(EXTENDED_STUDY_YEARS)-1)
    correction_poly = np.poly1d(coeffs)

    ratios = np.array([raw_ratio[year]*correction_poly(year) for year in years_list])

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


LEASING_TIER_BASE = "Full fee / Sin Subvención"
LEASING_TIER_SUBSIDY = "Full fee / 25% subsidy"


def load_leasing_tables(file, sheet_name="Leasing"):
    """
    Lee las dos franjas de leasing de la hoja 'Leasing': 'Full fee / Sin Subvención'
    (columnas D:I) y 'Full fee / 25% subsidy' (columnas J:O) -- misma estructura de
    filas (Leasing Scenario) x Client Rating (5-10) en ambas, desplazada 6 columnas.
    Hoy solo se usa la primera franja (vía '€ Leasing Monthly', ya calculado en el
    Excel); esto añade la segunda para poder comparar ambos casos en Scenario Results.

    Devuelve {tier_label: {leasing_scenario: {client_rating: fee_eur_month}}}.
    """

    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)
    ratings = raw.iloc[1, 3:9].astype(int).tolist()

    tables = {}
    for label, col_start in [(LEASING_TIER_BASE, 3), (LEASING_TIER_SUBSIDY, 9)]:
        table = {}
        for row_idx in range(2, len(raw)):
            leasing_scenario = raw.iloc[row_idx, 1]
            if pd.isna(leasing_scenario):
                continue
            fees = raw.iloc[row_idx, col_start:col_start + 6].tolist()
            table[leasing_scenario] = dict(zip(ratings, fees))
        tables[label] = table

    return tables


def leasing_fee(leasing_tables, tier, leasing_scenario, client_rating):
    try:
        return float(leasing_tables[tier][leasing_scenario][client_rating])
    except KeyError:
        raise ValueError(
            f"No hay tarifa de leasing '{tier}' para Leasing Scenario='{leasing_scenario}', "
            f"Client Rating={client_rating}."
        )


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

        # "Tolls" en el Excel es un Sí/No: Sí -> 1, No -> 0. Si la columna no existe
        # (Excel de escenarios aún no actualizado) o está vacía, por defecto 1 (con tolls,
        # el comportamiento de siempre).
        tolls_raw = row.get("Tolls")
        if "Tolls" not in row or pd.isna(tolls_raw):
            tolls = 1
        else:
            tolls = 1 if str(tolls_raw).strip().lower() in ("si", "sí", "s", "yes", "1") else 0

        # DoD% (Depth of Discharge): fracción de la capacidad nominal realmente
        # utilizable (Solax Trene 0.95, Risen+mg 1.00 -- ver scenario_builder.py). Si el
        # Excel de escenarios no trae la columna (versión antigua), por defecto 1.0 --
        # el comportamiento previo a este fix, sin recortar la capacidad nominal.
        dod_raw = row.get("Depth of Discharge (DoD) %")
        dod = float(dod_raw) if "Depth of Discharge (DoD) %" in row and pd.notna(dod_raw) else 1.0

        scenarios.append({
            "Scenario"          :   row["Scenario"],
            "Container Type"    :   container_type,
            "Provider"          :   provider,
            "Nominal Capacity"  :   float(row["Nominal Capacity"]),
            "N Containers"      :   float(row["N containers"]),
            "DoD %"             :   dod,
            "C-Factor"          :   float(row["C-Factor"]),
            "Tariff"            :   tariff,
            "PPA Mode"          :   row["Price mode from PV surplus"],
            "Surplus Strategy"  :   strategy,
            "PPA Price"         :   float(row["PV PPA Price for charging €/MWh"]),
            "PPA Improvement"   :   ppa_imp,
            "Discharge Cost"    :   float(row["Discharge Cost"]) if "Discharge Cost" in row and pd.notna(row.get("Discharge Cost")) else 0.0,
            "Cycles/Day"        :   float(row["Cycles/day"]),
            "tolls"             :   tolls,
            "€ Leasing Monthly" :   float(row["€ Leasing Monthly"]),
            "Study Type"        :   study_type,
            "Client Rating"     :   int(row["Client Rating"]),
            "Leasing Scenario"  :   row["Leasing Scenario"],
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
        "DoD %"             :   scenario["DoD %"],
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
    elif scenario["Surplus Strategy"] == "Solve (PBI logic)":
        model, results = pbi_logic_daily.opt_pbi_logic_daily(data, inputs)
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


def kpi_row_from_results(data_base, scenario, results, inputs, horizon_years, savings_threshold, extension_data=None, y1=None, leasing_tables=None):
    """
    Calcula KPIs y proyección de ahorro a partir de un año 1 YA resuelto: no vuelve a
    llamar a solve_scenario, para que tanto el sweep en paralelo (solve_and_analyze_scenarios)
    como una resolución interactiva suelta (Scenario Builder) puedan reutilizar el mismo
    resultado de año 1 sin resolver el MILP dos veces.

    Para "Extended study" sí resuelve el MILP una vez más por cada año de
    EXTENDED_STUDY_YEARS distinto de 1 (proyectados vía mwh_extension), porque esos años no
    se calculan en ningún otro sitio.

    Devuelve (kpi_row, savings_by_year): kpi_row es el dict con los KPIs agregados (para
    Scenario Results, con "€ Total Savings" incluyendo BESS + mejora PPA); savings_by_year
    es la serie año a año (no acumulada) de savings de BESS a lo largo del horizonte,
    SIN mejora PPA, para la página "Savings Projection" (comparable frente al histórico/PBI).
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

    calib_years = [y for y in EXTENDED_STUDY_YEARS if y != 1]
    savings_by_calib_year = {y: np.nan for y in calib_years}
    if study_type == "Extended study":
        if extension_data is None or y1 is None:
            raise ValueError(
                f"Scenario '{scenario["Scenario"]}': Study Type='Extended study' requiere "
                f"extension_data/y1 (ver load_extension_data / sweep_bess_sizes)."
            )
        data_by_year = project_year_data(data_base, extension_data, y1, years=calib_years)
        savings_by_calib_year = {y: _solve_scenario_year_savings(data_by_year[y], scenario) for y in calib_years}

        proyeccion = project_savings_extended(
            savings_y1=savings_y1, savings_by_calib_year=savings_by_calib_year,
            provider=scenario["Provider"], extension_data=extension_data, y1=y1,
            years=range(1, horizon_years+1),
        )
    else:
        proyeccion = project_savings(savings_y1=savings_y1, tariff=inputs["TARIFF"], container_type=container_type, pct_charge_pv=pct_charge_pv, years=range(1, horizon_years+1),)

    savings_bess_n_years = proyeccion.sum()
    savings_total_n_years = savings_bess_n_years + savings_ppa_n_years

    # Curva año a año (no acumulada) de savings de BESS a lo largo de la vida del
    # proyecto (año 1 para Base study; años de EXTENDED_STUDY_YEARS simulados + polinomio
    # para Extended study, vía 'proyeccion'). Solo BESS, sin mejora PPA: la forma/ratio de
    # 'proyeccion' está calibrada sobre savings de BESS puros (histórico simHist / años de
    # EXTENDED_STUDY_YEARS del
    # propio MILP), no sobre savings+PPA, así que sumarle la mejora PPA aquí distorsionaría
    # la curva -- y además dejaría de ser comparable frente al histórico/PBI, que es la
    # razón de ser de esta proyección. Se usa en la página "Savings Projection".
    savings_by_year = proyeccion.copy()
    savings_by_year.name = "SAVINGS_BESS"

    annual_leasing_cost = scenario["€ Leasing Monthly"]*n_containers*12
    if horizon_years > 15:
        leasing_total_n_years = annual_leasing_cost*15
    else:
        leasing_total_n_years = annual_leasing_cost*horizon_years

    savings_pct = ((savings_total_n_years - leasing_total_n_years) / leasing_total_n_years)*100

    # Comparativa con la franja "Full fee / 25% subsidy" de la hoja Leasing: mismo
    # savings_total_n_years (depende de la operación, no de la financiación), pero
    # coste de leasing más bajo -> % Savings vs Leasing más alto.
    annual_leasing_cost_subsidy = np.nan
    leasing_total_n_years_subsidy = np.nan
    savings_pct_subsidy = np.nan
    if leasing_tables is not None:
        monthly_fee_subsidy = leasing_fee(leasing_tables, LEASING_TIER_SUBSIDY, scenario["Leasing Scenario"], scenario["Client Rating"])
        annual_leasing_cost_subsidy = monthly_fee_subsidy*n_containers*12
        if horizon_years > 15:
            leasing_total_n_years_subsidy = annual_leasing_cost_subsidy*15
        else:
            leasing_total_n_years_subsidy = annual_leasing_cost_subsidy*horizon_years
        savings_pct_subsidy = ((savings_total_n_years - leasing_total_n_years_subsidy) / leasing_total_n_years_subsidy)*100

    apto_subsidy = savings_pct_subsidy > savings_threshold if not np.isnan(savings_pct_subsidy) else np.nan

    kpi_row = {
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
        **{f"€ Savings BESS y{y} (simulado)": savings_by_calib_year[y] for y in calib_years},
        f"€ Savings from BESS {horizon_years}y"             :   savings_bess_n_years,
        "€ Total Savings y1"                                :   savings_y1 + savings_ppa_annual,
        f"€ Total Savings {horizon_years}y"                 :   savings_total_n_years,
        "€ Annual Leasing"                                  :   annual_leasing_cost,
        f"€ Leasing {horizon_years}y"                       :   leasing_total_n_years,
        "% Savings vs Leasing"                              :   savings_pct,
        "(>%.0f%%)" % savings_threshold                     :   savings_pct > savings_threshold,
        "€ Annual Leasing (25% subsidy)"                    :   annual_leasing_cost_subsidy,
        f"€ Leasing {horizon_years}y (25% subsidy)"         :   leasing_total_n_years_subsidy,
        "% Savings vs Leasing (25% subsidy)"                :   savings_pct_subsidy,
        "(>%.0f%% subsidy)" % savings_threshold             :   apto_subsidy,
    }

    return kpi_row, savings_by_year


def _solve_scenario_combined(data_base, scenario, horizon_years, savings_threshold, extension_data=None, y1=None, leasing_tables=None):
    """
    Resuelve el año 1 UNA sola vez y devuelve tanto los resultados horarios crudos (para
    las páginas de visualización del dashboard) como la fila de KPIs/proyección de ahorro
    (para Scenario Results), evitando resolver el mismo escenario dos veces.
    """

    print(f"Solving: [{scenario["Scenario"]}]: {scenario["Container Type"]} x {scenario["N Containers"]} "
          f"= {scenario["Nominal Capacity"]*scenario["N Containers"]:.3f} MWh ({scenario.get("Study Type", "Base study")})")

    model, results, inputs = solve_scenario(data_base, scenario)
    kpi_row, savings_by_year = kpi_row_from_results(data_base, scenario, results, inputs, horizon_years, savings_threshold, extension_data, y1, leasing_tables)

    return scenario["Scenario"], results, inputs, scenario, kpi_row, savings_by_year


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
      - savings_projections: {name: pd.Series}, la curva año a año de savings de BESS
        estimados, sin mejora PPA (para la página "Savings Projection").

    Pensado para el botón único "Run Scenarios" del dashboard: antes había un solve por
    separado para visualización (solve_all_scenarios) y otro para el sweep de KPIs
    (sweep_bess_sizes), resolviendo el mismo año 1 dos veces.
    """

    scenarios = load_scenarios(file)
    if only is not None:
        scenarios = [s for s in scenarios if s["Scenario"] in set(only)]

    data_base = load_hourly_data(file)
    leasing_tables = load_leasing_tables(file)

    extension_data = None
    y1 = None
    if any(scen.get("Study Type", "Base study") == "Extended study" for scen in scenarios):
        tariff = read_cups_info(file)["Tariff"]
        extension_data = load_extension_data(file, tariff)
        y1 = int(data_base["Year"].dropna().iloc[0])

    if not parallel:
        raw = [_solve_scenario_combined(data_base, scen, horizon_years, savings_threshold, extension_data, y1, leasing_tables) for scen in scenarios]
    else:
        workers = n_workers or max(os.cpu_count() - 1, 1)
        raw = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_solve_scenario_combined, data_base, scen, horizon_years, savings_threshold, extension_data, y1, leasing_tables): scen["Scenario"]
                for scen in scenarios
            }
            for future in as_completed(futures):
                raw.append(future.result())

    scenario_results = {name: {"results": results, "inputs": inputs, "scenario": scenario} for name, results, inputs, scenario, kpi_row, savings_by_year in raw}
    kpi_rows = {name: kpi_row for name, results, inputs, scenario, kpi_row, savings_by_year in raw}
    savings_projections = {name: savings_by_year for name, results, inputs, scenario, kpi_row, savings_by_year in raw}

    return scenario_results, kpi_rows, savings_projections


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

    _, kpi_rows, _ = solve_and_analyze_scenarios(
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



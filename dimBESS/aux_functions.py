import numpy as np
import pandas as pd

def calculate_table(results, ppa_price, inputs):
    results_aux = results
    results_aux["Consumo Directo PV"] = np.where(results_aux["Producción PV"]>results_aux["Demanda"],results_aux["Demanda"],results_aux["Producción PV"])
    results_aux["Demanda tras PV"] = results_aux["Demanda"] - results_aux["Consumo Directo PV"]
    results_aux["Carga"] = results_aux["Carga de PV"] + results_aux["Carga de red"]
    results_aux["Date"] = pd.to_datetime(results_aux["Date&Time"])
    mwh_demand = float(results_aux["Demanda"].sum() - results_aux["Producción PV"][results_aux["Producción PV"]<0].sum())
    mwh_demand_phase1 = float(results_aux["Demanda tras PV"].sum())
    mwh_demand_phase2 = float(results_aux["Cobertura red"].sum())
    mwh_charge_pv = float(results_aux["Carga de PV"].sum())
    mwh_pv = float(results_aux["Consumo Directo PV"].sum())
    mwh_charge_grid = float(results_aux["Carga de red"].sum())
    mwh_discharge = float(results_aux["Descarga"].sum())
    perc_charge_pv = dividir(mwh_charge_pv,(mwh_charge_pv+mwh_charge_grid))*100
    perc_charge_grid = 100-perc_charge_pv

    cost = float((results_aux["Demanda"]*results_aux["Precio Red"]).sum())
    cost_grid_1 = float((results_aux["Demanda tras PV"]*results_aux["Precio Red"]).sum())
    cost_grid_2 = float((results_aux["Cobertura red"]*results_aux["Precio Red"]).sum())
    cost_charge_pv = float((results_aux["Carga de PV"]*results_aux["Precio Carga PV"]).sum())
    cost_charge_grid = float((results_aux["Carga de red"]*results_aux["Precio Carga Red sin Tolls"]).sum())
    cost_charge = cost_charge_pv+cost_charge_grid
    bess_replaced = float((results_aux["Descarga"]*results_aux["Precio Red"]).sum())
    replaced_price = dividir(bess_replaced,mwh_discharge)
    price_discharge = dividir(cost_charge,mwh_discharge)
    spread = replaced_price-price_discharge
    cost_pv_1 = mwh_pv*ppa_price
    cost_1 = cost_grid_1+cost_pv_1
    cost_2 = cost_grid_2+cost_pv_1+cost_charge

    eur_mwh = dividir(cost,mwh_demand)
    eur_mwh_1 = dividir(cost_1,mwh_demand)
    eur_mwh_2 = dividir(cost_2,mwh_demand)
    eur_grid_1 = dividir(cost_grid_1,mwh_demand_phase1)
    eur_grid_2 = dividir(cost_grid_2,mwh_demand_phase2)
    eur_pv = dividir(cost_pv_1,mwh_pv)
    eur_charge_pv = dividir(cost_charge_pv,mwh_charge_pv)
    eur_charge_grid = dividir(cost_charge_grid,mwh_charge_grid)
    eur_discharge = dividir(cost_charge,mwh_discharge)
    eur_charge = dividir(cost_charge,(mwh_charge_grid+mwh_charge_pv))
    kpi_bess_ut = dividir((mwh_charge_grid+mwh_charge_pv),(inputs["N containers"]*inputs["Pot BESS"]*inputs["DoD %"]*inputs["Cycles/Day"]*(results["BESS Degradation factor"].sum())/24))*100
    max_spread = (results_aux.groupby(results_aux["Date"].dt.date)["Precio Red"].agg(lambda x: x.max() - x.min()).mean())
    kpi_cap_spread = dividir(spread,max_spread)*100

    cover_1 = dividir(mwh_pv,mwh_demand)*100
    cover_2 = dividir((mwh_pv+mwh_discharge),mwh_demand)*100
    bess_cover = dividir(mwh_discharge,mwh_demand)*100
    pv_ac_1 = dividir(mwh_pv,(results_aux["Producción PV"].sum()))*100
    pv_ac_2 = dividir((mwh_pv+mwh_charge_pv),(results_aux["Producción PV"].sum()))*100
    pv_bess = dividir(mwh_charge_pv,(results_aux["Producción PV"].sum()))*100

    savings_1 = cost-cost_1
    savings_2 = cost-cost_2
    savings_bess = savings_2-savings_1

    days = len(results_aux)/24
    charging_hours = len(results_aux[results_aux["Carga"]>0])
    charging_hours_day = charging_hours/days
    cycles = days*kpi_bess_ut/100
    kpi_charge_opt = (1/charging_hours_day)/inputs["C-factor"]*100

    calc_data = {
        "MWh Demand"                        :   mwh_demand,
        "MWh Unmet Demand after Direct SC"  :   mwh_demand_phase1,
        "MWh Unmet Demand after BESS"       :   mwh_demand_phase2,
        "MWh Charge from PV"                :   mwh_charge_pv,
        "MWh PV Direct SC"                  :   mwh_pv,
        "MWh Charge from Grid"              :   mwh_charge_grid,
        "MWh BESS Discharge"                :   mwh_discharge,
        "% Charge from PV"                  :   perc_charge_pv,
        "% Charge from Grid"                :   perc_charge_grid,
        "€ Cost As-Is"                      :   cost,
        "€ Total Cost Phase 1"              :   cost_1,
        "€ Total Cost Phase 2"              :   cost_2,
        "€ Cost Grid Phase 1"               :   cost_grid_1,
        "€ Cost Grid Phase 2"               :   cost_grid_2,
        "€ Cost charging from PV"           :   cost_charge_pv,
        "€ Cost charging from Grid"         :   cost_charge_grid,
        "€ Cost charging"                   :   cost_charge,
        "€ BESS Replaced Cost"              :   bess_replaced,
        "€/MWh BESS Replaced Price"         :   replaced_price,
        "€/MWh BESS Discharge"              :   price_discharge,
        "€/MWh BESS Captured Spread"        :   spread,
        "€ Cost PV Direct SC"               :   cost_pv_1,
        "€/MWh As-Is"                       :   eur_mwh,
        "€/MWh Total Cost Phase 1"          :   eur_mwh_1,
        "€/MWh Total Cost Phase 2"          :   eur_mwh_2,
        "€/MWh Phase 1 Grid"                :   eur_grid_1,
        "€/MWh Phase 2 Grid"                :   eur_grid_2,
        "€/MWh PV Direct SC"                :   eur_pv,
        "€/MWh Charge from PV"              :   eur_charge_pv,
        "€/MWh Charge from Grid"            :   eur_charge_grid,
        "€/MWh Charge Blended"              :   eur_charge,
        "€/MWh BESS Discharge"              :   eur_discharge,
        "€/MWh Max Grid Pot. Spread"        :   max_spread,
        "KPI Captured Spread"               :   kpi_cap_spread,
        "KPI Charging Optimization"         :   kpi_charge_opt,
        "KPI BESS Utilization (Cycles/Day)" :   kpi_bess_ut,
        "% Cover Phase 1"                   :   cover_1,
        "% Cover Phase 2"                   :   cover_2,
        "% BESS Demand cover"               :   bess_cover,
        "% Direct PV Self-consumption"      :   pv_ac_1,
        "% Total PV Self-consumption"       :   pv_ac_2,
        "% BESS PV Self-consumption"        :   pv_bess,
        "€ Total Savings Phase 1"           :   savings_1,
        "€ Total Savings Phase 2"           :   savings_2,
        "€ Savings from BESS"               :   savings_bess,
        "# Days"                            :   days,
        "# Charging hours"                  :   charging_hours,
        "# Charging hours / Day"            :   charging_hours_day,
        "# C/D Hours by C-Factor"           :   1/inputs["C-factor"],
        "# BESS Cycles"                     :   cycles
    }

    return(calc_data)


def chart_title(text, bg_color=None, size_max=14):
    """
    Título para cualquier gráfico Plotly (gauge, pie, etc.), como HTML normal en vez del
    title= interno de Plotly: ese es texto SVG de ancho fijo que no envuelve, así que en
    una columna estrecha un título largo ("Demand Cover by Source (%)") se recorta por
    ambos lados en vez de saltar de línea. Va justo encima del gráfico (que se crea sin
    su propio title=).
    """

    bg_style = f"background-color:{bg_color}; padding:4px 0;" if bg_color else ""

    return f"""
    <div style="{bg_style} text-align:center; font-size:clamp(10px, 1.1vw, {size_max}px); font-weight:600; color:grey; overflow-wrap:break-word;">
        {text}
    </div>
    """


def gauge_title(text):
    return chart_title(text)


def metric_cell(value, label, decimals=2, bg_color=None, suffix=""):
    if value is None:
        return "&nbsp;"

    bg_style = f"background-color:{bg_color}; padding:6px; border-radius:6px;" if bg_color else ""

    # clamp() en vez de px fijos: mismo tamaño máximo de siempre en pantallas anchas,
    # pero encoge en vez de desbordar cuando la columna que lo contiene es estrecha.
    return f"""
    <div style="{bg_style} line-height:1.25; min-width:0;">
        <div style="font-size:clamp(10px, 1.3vw, 16px); font-weight:600; overflow-wrap:break-word;">
            {value:,.{decimals}f}{suffix}
        </div>
        <div style="font-size:clamp(8px, 0.85vw, 12px); color:gray; overflow-wrap:break-word;">
            {label}
        </div>
    </div>
    """

def column_card(rows, bg_color=None, min_height=None):
    """
    Una tarjeta de columna: varias metric_cell apiladas dentro de un único
    contenedor con un solo fondo de color (en vez de colorear cada celda por
    separado), para que la columna entera se lea como un bloque sólido.

    rows: lista de (value, label[, decimals=2][, suffix=""]); None para un hueco.
    """
    cells_html = ""
    for row in rows:
        if row is None:
            cells_html += "<div>&nbsp;</div>"
            continue
        value, label = row[0], row[1]
        decimals = row[2] if len(row) > 2 else 2
        suffix = row[3] if len(row) > 3 else ""
        # metric_cell() vuelve con saltos de línea + indentación; si se concatenan
        # varias dentro de un mismo st.markdown, Markdown interpreta esa indentación
        # como bloque de código a partir de la segunda celda. Lo aplanamos a una línea.
        cells_html += " ".join(metric_cell(value, label, decimals, None, suffix).split())

    bg_style = f"background-color:{bg_color}; padding:10px 12px; border-radius:8px;" if bg_color else "padding:10px 12px;"
    height_style = f" min-height:{min_height}px;" if min_height else ""

    return f'<div style="{bg_style}{height_style}">{cells_html}</div>'

def dividir(num, den):
    if ((den==0) | pd.isna(num) | pd.isna(den)):
        return 0
    return num/den

def freq_kpis(results, inputs, freq):

    results_aux = results

    results_aux["Date"] = pd.to_datetime(results_aux["Date&Time"])
    results_aux["Carga"] = results_aux["Carga de PV"] + results_aux["Carga de red"]
    results_aux["Hora Carga"] = np.where(results_aux["Carga"],1,0)

    max_spread = (results_aux.groupby(results_aux["Date"].dt.date)["Precio Red"].agg(lambda x: x.max() - x.min()))
    min_charge = (results_aux.groupby(results_aux["Date"].dt.date)["Precio Red"].agg(lambda x: x.min()))
    max_replace = (results_aux.groupby(results_aux["Date"].dt.date)["Precio Red"].agg(lambda x: x.max()))
    days = max_spread/max_spread            ####------ESTO TIENE QUE HABER ALGUNA FORMA MAS FINA DE HACERLO
    max_spread.index = pd.to_datetime(max_spread.index)
    min_charge.index = pd.to_datetime(min_charge.index)
    max_replace.index = pd.to_datetime(max_replace.index)
    days.index = pd.to_datetime(days.index)
    max_spread = max_spread.resample(freq).mean()
    min_charge = min_charge.resample(freq).mean()
    max_replace = max_replace.resample(freq).mean()
    days = days.resample(freq).sum()

    bess_replaced = results_aux["Descarga"]*results_aux["Precio Red"]
    bess_replaced.index = results_aux["Date"]
    bess_replaced = bess_replaced.resample(freq).sum()
    cost_charge_pv = results_aux["Carga de PV"]*results_aux["Precio Carga PV"]
    cost_charge_grid = results_aux["Carga de red"]*results_aux["Precio Carga Red sin Tolls"]
    cost_charge = cost_charge_pv+cost_charge_grid
    cost_charge.index = results_aux["Date"]
    cost_charge = cost_charge.resample(freq).sum()
    mwh_discharge = results_aux["Descarga"]
    mwh_discharge.index = results_aux["Date"]
    mwh_discharge = mwh_discharge.resample(freq).sum()
    replaced_price = bess_replaced/mwh_discharge
    price_discharge = cost_charge/mwh_discharge
    spread = replaced_price-price_discharge

    mwh_charge_pv = results_aux["Carga de PV"]
    mwh_charge_grid = results_aux["Carga de red"]
    mwh_charge = mwh_charge_grid+mwh_charge_pv
    mwh_charge.index = results_aux["Date"]
    mwh_charge = mwh_charge.resample(freq).sum()
    deg = results["BESS Degradation factor"]
    deg.index = results["Date"]
    deg = deg.resample(freq).mean()
    kpi_bess_ut = ((mwh_charge)/(inputs["N containers"]*inputs["Pot BESS"]*inputs["DoD %"]*inputs["Cycles/Day"]*deg*days))*100
    cycles = days*kpi_bess_ut/100

    charging_hours = results_aux["Hora Carga"]
    charging_hours.index = results_aux["Date"]
    charging_hours = charging_hours.resample(freq).sum()
    charging_hours_day = charging_hours/days
    kpi_charge_opt = (1/charging_hours_day)/inputs["C-factor"]*100

    results_freq = pd.DataFrame(index=max_spread.index)
    results_freq["€/MWh AVG Min Price to Charge"] = min_charge
    results_freq["€/MWh AVG Max Price to Replace"] = max_replace
    results_freq["€/MWh Max Grid Pot. Spread"] = max_spread
    results_freq["€/MWh BESS Captured Spread"] = spread
    results_freq["# Days"] = days
    results_freq["# BESS Cycles"] = cycles
    results_freq["KPI BESS Utilization (Cycles/Day)"] = kpi_bess_ut
    results_freq["# Charging hours / Day"] = charging_hours_day
    results_freq["# C/D Hours by C-Factor"] = 1/inputs["C-factor"]
    results_freq["KPI Charging Optimization"] = kpi_charge_opt

    return(results_freq)




# Hora (0-23) a partir de la cual la ventana de carga se cierra si no hay excedente de PV más
# tarde ese día: t_end = max(suelo, última hora con excedente PV). Es el mismo criterio que
# usan los motores de resolución (best_price_daily.py y pv_first_daily.py: 16;
# pbi_logic_daily.py: 15). Si cambia allí, hay que cambiarlo aquí.
CHARGE_WINDOW_FLOOR_HOUR = {"Solve (PBI logic)": 15}
CHARGE_WINDOW_FLOOR_HOUR_DEFAULT = 16


def contracted_power_analysis(results, data_base, inputs, delta_power=0.0, strategy=None):
    """
    Cuánto limita la potencia contratada a la carga desde red, hora a hora y por periodo.

    Hueco de una hora = max(ContPower - demanda no cubierta por el PV, 0) -- misma definición
    que el "Cap by ContPower from grid" de PBI. Capacidad de carga desde red de esa hora =
    min(hueco, potencia de carga de la batería), contada solo en las horas de la ventana de
    carga (fuera de ella el despacho no permite cargar, así que no es capacidad real).

    delta_power (MW) suma/resta potencia contratada en todas las horas (sensibilidad: no
    re-resuelve el despacho, la carga real no cambia; para el efecto sobre el ahorro, ver
    dimBESS.contracted_power_marginal_value). strategy elige el suelo de la ventana de carga.

    Devuelve (por_periodo, horario).
    """

    n = (min(len(data_base), len(results))//24)*24
    data = data_base.reset_index(drop=True).iloc[:n]
    res = results.reset_index(drop=True).iloc[:n]

    pch_max = inputs["Pot BESS"]*inputs["N containers"]*inputs["DoD %"]*inputs["C-factor"]
    tol = 1e-6

    # Ventana de carga por día (misma regla que los modelos).
    floor_hour = CHARGE_WINDOW_FLOOR_HOUR.get(strategy, CHARGE_WINDOW_FLOOR_HOUR_DEFAULT)
    # Una fila por día (reshape(-1, 24)): pv_surplus[d, h] es el excedente PV de la hora h del día d, y
    # todas las operaciones con axis=1 se hacen por día, igual que el bucle por días de los solvers.
    pv_surplus = np.maximum(res["Producción PV"].values - res["Demanda"].values, 0).reshape(-1, 24)
    has_surplus = pv_surplus > 0
    # Última hora (0-23) con excedente PV de cada día, o -1 si ese día no hay excedente.
    last_pv = np.where(has_surplus.any(axis=1), 23 - np.argmax(has_surplus[:, ::-1], axis=1), -1)
    # Fin de ventana por día. El tope 23 es solo una guarda (equivale al nh-1 de los solvers, que protege
    # un último bloque incompleto): con datos reales last_pv nunca supera ~19, así que no actúa.
    t_end = np.minimum(np.maximum(floor_hour, last_pv), 23)
    in_window = (np.arange(24)[None, :] <= t_end[:, None]).reshape(-1)

    hourly = pd.DataFrame({
        "Fecha"         :   pd.to_datetime(data["Date&Time"]).dt.date.values,
        "Periodo"       :   data["Period"].values,
        "Hora"          :   data["HourOfDay"].values,
        "Mes"           :   data["Month num"].values,
        "Potencia contratada (MW)"  :   data["Cont Power MW"].values + delta_power,
        "En ventana"    :   in_window,
    })
    contract = hourly["Potencia contratada (MW)"]
    unmet = (res["Demanda"] - res["Producción PV"]).clip(lower=0).values
    hourly["Demanda no cubierta por PV (MW)"] = unmet
    # Importación para demanda = ImportDemand del modelo ("Cobertura red"). El despacho impone
    # ImportDemand + CargaRed <= PotenciaContratada en cada hora, así que el hueco tras demanda
    # es contratada - ImportDemand, y la carga de red nunca puede superarlo.
    import_demand = res["Cobertura red"].values
    hourly["Hueco (MW)"] = (contract - import_demand).clip(lower=0)
    hourly["Potencia de carga BESS (MW)"] = pch_max
    hourly["Capacidad de carga (MWh)"] = hourly["Hueco (MW)"].clip(upper=pch_max).where(hourly["En ventana"], 0.0)
    hourly["Carga red real (MWh)"] = res["Carga de red"].values
    hourly["Carga PV real (MWh)"] = res["Carga de PV"].values
    hourly["Carga total (MWh)"] = hourly["Carga red real (MWh)"] + hourly["Carga PV real (MWh)"]
    hourly["Hueco libre (MW)"] = (hourly["Hueco (MW)"] - hourly["Carga red real (MWh)"]).clip(lower=0)
    # Precio sombra de la potencia contratada (€ por MW extra en esa hora), solo si el despacho es un LP/MILP que lo calculó.
    if "Valor marginal potencia (€/MW)" in res.columns:
        hourly["Valor marginal (€/MW)"] = res["Valor marginal potencia (€/MW)"].values
    # Importación total de red = lo que se sigue pidiendo a red tras PV y BESS + lo que se
    # carga de red: es lo que consume potencia contratada.
    hourly["Importación demanda (MW)"] = import_demand
    hourly["Importación total (MW)"] = import_demand + hourly["Carga red real (MWh)"].values
    hourly["Necesaria para cargar a plena potencia (MW)"] = unmet + pch_max

    charging = hourly["Carga red real (MWh)"] > tol
    hourly["Limitada por contrato"] = charging & (hourly["Carga red real (MWh)"] >= hourly["Hueco (MW)"] - tol) & (hourly["Hueco (MW)"] < pch_max - tol)
    hourly["Limitada por BESS"] = charging & (hourly["Carga red real (MWh)"] >= pch_max - tol)
    # Tope superior de lo que el contrato impide cargar (no todo se habría usado: el
    # presupuesto diario de carga también manda).
    hourly["Carga bloqueada por contrato (MWh)"] = (pch_max - hourly["Carga red real (MWh)"]).where(hourly["Limitada por contrato"], 0.0)
    hourly["Sin hueco"] = hourly["Hueco (MW)"] <= tol
    hourly["Demanda > contrato"] = unmet > contract + tol
    hourly["Demanda >= 95% contrato"] = unmet >= 0.95*contract
    # "Saturada" = importación igual a la contratada con tolerancia de 1 kW. El despacho deja ruido numérico de ~1e-4 kWh,
    # así que comparar con 0 exacto cuenta mal (Kappa 2 contenedores: 39 horas con holgura exactamente 0 frente a 147
    # reales; no hay ninguna hora con holgura entre 1 W y 10 kW, así que la tolerancia no es sensible).
    hourly["Importando al contrato"] = hourly["Importación total (MW)"] >= contract - 1e-3
    hourly["Saturada en ventana"] = hourly["En ventana"] & hourly["Importando al contrato"]
    # Saturación dividida según haya o no carga de red del BESS en esa hora.
    hourly["Saturada por demanda"] = hourly["Saturada en ventana"] & ~charging
    hourly["Saturada con carga BESS"] = hourly["Saturada en ventana"] & charging
    hourly["Capacidad libre (MW)"] = (contract - hourly["Importación total (MW)"]).clip(lower=0)
    hourly["Importando >= 95% contrato"] = hourly["Importación total (MW)"] >= 0.95*contract
    hourly["Hueco >= potencia BESS"] = hourly["Hueco (MW)"] >= pch_max - tol

    g = hourly.groupby("Periodo")
    gw = hourly[hourly["En ventana"]].groupby("Periodo")  # métricas de carga: solo horas donde se puede cargar

    by_period = pd.DataFrame({
        "Horas en ventana"              :   gw.size(),
        # La potencia contratada es constante dentro de un periodo (viene de un lookup
        # periodo -> MW), así que first() es exacto, no una media.
        "Potencia contratada (MW)"      :   g["Potencia contratada (MW)"].first(),
        "Capacidad (MWh)"               :   g["Capacidad de carga (MWh)"].sum(),
        "Carga de red (MWh)"            :   g["Carga red real (MWh)"].sum(),
        "Carga PV (MWh)"                :   g["Carga PV real (MWh)"].sum(),
        "Importación demanda (MWh)"     :   g["Importación demanda (MW)"].sum(),
        # Importación máxima potencial = potencia contratada x todas las horas del periodo en el año.
        "Capacidad total (MWh)"         :   g["Potencia contratada (MW)"].sum(),
        "Horas saturadas (ventana)"     :   g["Saturada en ventana"].sum().astype(int),
        "Horas saturadas por demanda"   :   g["Saturada por demanda"].sum().astype(int),
        "Horas saturadas con carga BESS":   g["Saturada con carga BESS"].sum().astype(int),
        # Métricas "en horas de carga" (ventana de carga): capacidad, carga e importación solo ahí.
        "Capacidad en ventana (MWh)"    :   gw["Potencia contratada (MW)"].sum(),
        "Capacidad tras demanda (MWh)"  :   gw["Hueco (MW)"].sum(),
        "Carga de red en ventana (MWh)" :   gw["Carga red real (MWh)"].sum(),
        "Importación demanda ventana (MWh)": gw["Importación demanda (MW)"].sum(),
        "Importación total ventana (MWh)":  gw["Importación total (MW)"].sum(),
        "Capacidad libre media (MW)"    :   gw["Capacidad libre (MW)"].mean(),
        "Horas de ventana con hueco"    :   gw["Importando al contrato"].apply(lambda x: int((~x).sum())),
        "Horas con carga de red (ventana)": gw["Carga red real (MWh)"].apply(lambda x: int((x > tol).sum())),
        "Horas con carga (red o PV)"    :   g["Carga total (MWh)"].apply(lambda x: int((x > tol).sum())),
        "Horas con carga"               :   g["Carga red real (MWh)"].apply(lambda x: int((x > tol).sum())),
        "Horas limitadas (contrato)"    :   g["Limitada por contrato"].sum().astype(int),
        "Horas limitadas (BESS)"        :   g["Limitada por BESS"].sum().astype(int),
        "Bloqueada por contrato (MWh)"  :   g["Carga bloqueada por contrato (MWh)"].sum(),
        "Pico demanda (MW)"             :   g["Demanda no cubierta por PV (MW)"].max(),
        "Pico importación (MW)"         :   g["Importación total (MW)"].max(),
        "Horas al límite"               :   g["Importando al contrato"].sum().astype(int),
        "Horas ≥95%"                    :   g["Importando >= 95% contrato"].sum().astype(int),
        "Horas demanda ≥95%"            :   g["Demanda >= 95% contrato"].sum().astype(int),
        "Horas demanda > contrato"      :   g["Demanda > contrato"].sum().astype(int),
        "Horas sin hueco"               :   gw["Sin hueco"].sum().astype(int),
        "Hueco ≥ BESS (% horas)"        :   gw["Hueco >= potencia BESS"].mean()*100,
        "Necesaria P50 (MW)"            :   gw["Necesaria para cargar a plena potencia (MW)"].quantile(0.5),
        "Necesaria P90 (MW)"            :   gw["Necesaria para cargar a plena potencia (MW)"].quantile(0.9),
    })
    by_period["Capacidad en ventana / total (%)"] = by_period["Capacidad en ventana (MWh)"]/by_period["Capacidad total (MWh)"].replace(0, np.nan)*100
    by_period["Carga / capacidad en ventana (%)"] = by_period["Carga de red en ventana (MWh)"]/by_period["Capacidad en ventana (MWh)"].replace(0, np.nan)*100
    by_period["Carga / capacidad tras demanda (%)"] = by_period["Carga de red en ventana (MWh)"]/by_period["Capacidad tras demanda (MWh)"].replace(0, np.nan)*100
    by_period["Capacidad libre / máxima (%)"] = (by_period["Capacidad en ventana (MWh)"] - by_period["Importación total ventana (MWh)"]).clip(lower=0)/by_period["Capacidad en ventana (MWh)"].replace(0, np.nan)*100
    by_period["Saturación por demanda (%)"] = by_period["Horas saturadas por demanda"]/by_period["Horas en ventana"].replace(0, np.nan)*100
    by_period["Saturación con carga BESS (%)"] = by_period["Horas saturadas con carga BESS"]/by_period["Horas en ventana"].replace(0, np.nan)*100
    by_period["Saturación / horas con carga (%)"] = by_period["Horas saturadas con carga BESS"]/by_period["Horas con carga de red (ventana)"].replace(0, np.nan)*100
    by_period["Saturación / horas con carga total (%)"] = by_period["Horas saturadas con carga BESS"]/by_period["Horas con carga (red o PV)"].replace(0, np.nan)*100
    by_period["Saturación ventana (%)"] = by_period["Horas saturadas (ventana)"]/by_period["Horas en ventana"].replace(0, np.nan)*100
    by_period["Libre (MWh)"] = (by_period["Capacidad (MWh)"] - by_period["Carga de red (MWh)"]).clip(lower=0)
    by_period["Utilización (%)"] = by_period["Carga de red (MWh)"]/by_period["Capacidad (MWh)"].replace(0, np.nan)*100
    by_period["Pico / contrato (%)"] = by_period["Pico importación (MW)"]/by_period["Potencia contratada (MW)"]*100
    by_period["Déficit P90 (MW)"] = (by_period["Necesaria P90 (MW)"] - by_period["Potencia contratada (MW)"]).clip(lower=0)
    by_period = by_period.sort_index()

    return by_period, hourly

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
    cost_charge_grid = float((results_aux["Carga de red"]*results_aux["Precio Carga Red"]).sum())
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
    kpi_bess_ut = dividir((mwh_charge_grid+mwh_charge_pv),(inputs["N containers"]*inputs["Pot BESS"]*inputs["Cycles/Day"]*(results["BESS Degradation factor"].sum())/24))*100
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


def metric_cell(value, label, decimals=2, bg_color=None, suffix=""):
    if value is None:
        return "&nbsp;"

    bg_style = f"background-color:{bg_color}; padding:6px; border-radius:6px;" if bg_color else ""

    return f"""
    <div style="{bg_style} line-height:1.25;">
        <div style="font-size:16px; font-weight:600;">
            {value:,.{decimals}f}{suffix}
        </div>
        <div style="font-size:12px; color:gray;">
            {label}
        </div>
    </div>
    """

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
    cost_charge_grid = results_aux["Carga de red"]*results_aux["Precio Carga Red"]
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
    kpi_bess_ut = ((mwh_charge)/(inputs["N containers"]*inputs["Pot BESS"]*inputs["Cycles/Day"]*deg*days))*100
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



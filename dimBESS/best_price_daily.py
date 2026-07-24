import pandas as pd
from pyomo.environ import *
from pyomo.environ import SolverFactory
from pyomo.environ import Expression
import numpy as np


def _economic_cost(m, grid_price, grid_charge_price, pv_price, discharge_cost):
    return sum(
        m.ImportDemand[t] * grid_price[t]
        + m.Gch[t] * grid_charge_price[t]
        + m.PVch[t] * pv_price[t]
        + m.Bdis[t] * discharge_cost
        for t in m.T
    )


def _build_daily_model(
    demand,
    pv_prod,
    pv_price,
    pot_contratada,
    grid_price,
    grid_charge_price,
    discharge_cost,
    eta_dis,
    soc_max_effective,
    pv_surplus,
    window,
    soc_init,
    charge_budget,
    PCH_MAX,
    PDIS_MAX,
    SOC_MIN,
):
    """
    MILP para un bloque de T horas (T=24 en los días completos,
    T<24 en el bloque inicial/final por el offset 6:00->6:00).
    soc_max_effective: vector recortado de la serie anual para este bloque.
    """

    T = len(demand)
    model = ConcreteModel()
    model.T = RangeSet(0, T - 1)

    model.Gch = Var(model.T, within=NonNegativeReals, bounds=(0, PCH_MAX))
    model.PVch = Var(model.T, within=NonNegativeReals, bounds=(0, PCH_MAX))
    model.Bdis = Var(model.T, within=NonNegativeReals, bounds=(0, PDIS_MAX))
    model.u = Var(model.T, within=Binary)

    def importdemand_bounds(m, t):
        unmet_demand = demand[t] - pv_prod[t]
        upper_bound = unmet_demand if unmet_demand > 0 else 0
        return (0, upper_bound)

    model.ImportDemand = Var(model.T, within=NonNegativeReals, bounds=importdemand_bounds)

    def soc_bounds(m, t):
        return (SOC_MIN, soc_max_effective[t])

    model.SOC = Var(model.T, within=NonNegativeReals, bounds=soc_bounds)

    model.soc0 = Constraint(
        expr=model.SOC[0]
        == soc_init + ((model.Gch[0] + model.PVch[0]) - model.Bdis[0] / eta_dis[0])
    )

    def soc_rest_rule(m, t):
        return m.SOC[t] == m.SOC[t - 1] + (
            (m.Gch[t] + m.PVch[t]) - m.Bdis[t] / eta_dis[t]
        )

    model.soc_rest = Constraint(RangeSet(1, T - 1), rule=soc_rest_rule)

    def pvch_limit_rule(m, t):
        return m.PVch[t] <= pv_surplus[t]

    model.pvch_limit = Constraint(model.T, rule=pvch_limit_rule)

    def import_limit_rule(m, t):
        return m.ImportDemand[t] >= demand[t] - pv_prod[t] - m.Bdis[t]

    model.import_lb_cons = Constraint(model.T, rule=import_limit_rule)

    def pot_limit(m, t):
        return m.ImportDemand[t] + m.Gch[t] <= pot_contratada[t]

    model.pot_limit = Constraint(model.T, rule=pot_limit)

    def pvch_capacity_rule(m, t):
        return m.PVch[t] <= soc_max_effective[t] - m.SOC[t]

    model.pvch_capacity = Constraint(model.T, rule=pvch_capacity_rule)

    def no_simul_chdis_1(m, t):
        return m.Gch[t] + m.PVch[t] <= PCH_MAX * m.u[t]

    model.no_simul_1 = Constraint(model.T, rule=no_simul_chdis_1)

    def no_simul_chdis_2(m, t):
        return m.Bdis[t] <= PDIS_MAX * (1 - m.u[t])

    model.no_simul_2 = Constraint(model.T, rule=no_simul_chdis_2)

    def charge_window_rule(m, t):
        if window[t] == 1:
            return m.Gch[t] + m.PVch[t] <= PCH_MAX
        else:
            return m.Gch[t] + m.PVch[t] == 0

    model.charge_window = Constraint(model.T, rule=charge_window_rule)

    def discharge_window_rule(m, t):
        if window[t] == 1:
            return m.Bdis[t] == 0
        else:
            return m.Bdis[t] <= PDIS_MAX

    model.discharge_window = Constraint(model.T, rule=discharge_window_rule)

    def ciclos_cap_rule(m):
        return sum(m.Gch[t] + m.PVch[t] for t in m.T) <= charge_budget

    model.ciclos_cap = Constraint(rule=ciclos_cap_rule)

    def obj_rule(m):
        return _economic_cost(m, grid_price, grid_charge_price, pv_price, discharge_cost)

    model.obj = Objective(rule=obj_rule, sense=minimize)
    return model


def _solve(model, tee=False):
    solver = SolverFactory("cbc")
    result = solver.solve(model, tee=tee)
    term = result.solver.termination_condition
    if term not in (TerminationCondition.optimal, TerminationCondition.feasible):
        raise RuntimeError(f"Solver terminó con condición: {term}")
    return result


def _extract_results(model, demand, pv_prod, eta_dis, pv_price, grid_price, grid_charge_price):

    T = len(demand)

    return {
        "Demanda"           :   demand,
        "Producción PV"     :   pv_prod,
        "RTE Efficiency"    :   eta_dis,
        "Carga de PV"       :   [model.PVch[t]() for t in range(T)],
        "Carga de red"      :   [model.Gch[t]() for t in range(T)],
        "Precio Carga PV"   :   pv_price,
        "Precio Carga Red"  :   grid_charge_price,
        "Precio Red"        :   grid_price,
        "SOC"               :   [model.SOC[t]() for t in range(T)],
        "Descarga"          :   [model.Bdis[t]() for t in range(T)],
        "Cobertura red"     :   [model.ImportDemand[t]() for t in range(T)],
    }


def opt_best_price_daily(data, inputs, tee=False):
    """
    Resuelve el año iterando día a día (T=24 × 365), replicando la lógica de
    bloques/ventanas de pv_first_daily, pero con el objetivo de coste puro
    de best_price (sin sesgo de priorización de la carga PV).

    Series anuales (8760) se recortan por día; el índice diario t corresponde
    a la hora global start + t (p. ej. día 100 → horas 2400–2423).
    """

    HOURS_PER_DAY = 24
    OFFSET = 0
    E_MAX = inputs["Pot BESS"]*inputs["N containers"]

    demand = (data["Power demand kWh"]/1000).tolist()
    pv_prod = (data["PV Generation kWh"]/1000).tolist()
    pot_contratada = data["Cont Power MW"].tolist()
    grid_price = data["Final Prices"].tolist()
    discharge_cost = inputs["Discharge Cost"]
    pv_price_mode = inputs["PPA Mode"]
    if pv_price_mode == "Free":
        pv_price = [0.0]*len(demand)
    elif pv_price_mode == "PPA fixed price":
        pv_price = [inputs["PPA Price"]]*len(demand)
    elif pv_price_mode == "Merch compensation":
        pv_price = data["Pool price"].tolist()
    else:
        raise ValueError(f"pv_price_mode desconocido: {pv_price_mode}")
    deg = data["BESS Degradation factor"]
    soc_max_effective = (E_MAX * deg).tolist()
    eta_dis = data["RTE Efficiency"].tolist()
    tolls = inputs["tolls"]

    if tolls == 0:
        grid_charge_price = (data["Final Prices"] - data["Tolls and RC"]).tolist()
    elif tolls == 1:
        grid_charge_price = data["Final Prices"].tolist()
    else:
        raise ValueError(f"tolls desconocido: {tolls}")

    check = pd.DataFrame({
        "Demand"    :   demand,
        "PV Prod"   :   pv_prod,
        "Pot"       :   pot_contratada,
    })
    check["Import"] = check["Demand"] - check["PV Prod"]

    mask = check["Import"] > check["Pot"]
    if mask.any():
        hours = check.index[mask].tolist()
        days = sorted({int((h +1) // 24) for h in hours})

        print(f"WARNING: Potential infeasibility detected.")
        print(f"Hours: {hours}")
        print(f"Located in day(s): {days}")

    T = len(demand)
    if T % HOURS_PER_DAY != 0:
        raise ValueError(f"T={T} no es múltiplo de {HOURS_PER_DAY}")

    pv_surplus = [max(pv_prod[t] - demand[t], 0) for t in range(T)]

    blocks = []
    if OFFSET >0:
        blocks.append((0, OFFSET))

    n_full_days = (T - OFFSET) // HOURS_PER_DAY
    for d in range(n_full_days):
        start = OFFSET + d*HOURS_PER_DAY
        blocks.append((start, HOURS_PER_DAY))

    tail_start = OFFSET + n_full_days*HOURS_PER_DAY
    tail_len = T - tail_start
    if tail_len > 0:
        blocks.append((tail_start, tail_len))

    assert sum(nh for _, nh in blocks) == T

    soc_init = 0.0
    all_results = []

    for i, (start, nh) in enumerate(blocks):
        print(f"block {i}: start={start} len{nh}")
        sl = slice(start, start + nh)

        pv_day = np.array(pv_surplus[sl])
        idx = np.where(pv_day>0)[0]
        last_pv = idx[-1] if len(idx) > 0 else -1
        t_end = min(max(16, last_pv), nh - 1)

        window = np.zeros(nh)
        window[:t_end+1] = 1

        model = _build_daily_model(
            demand=demand[sl],
            pv_prod=pv_prod[sl],
            pv_price=pv_price[sl],
            pot_contratada=pot_contratada[sl],
            grid_price=grid_price[sl],
            grid_charge_price=grid_charge_price[sl],
            discharge_cost=discharge_cost,
            eta_dis=eta_dis[sl],
            soc_max_effective=soc_max_effective[sl],
            pv_surplus=pv_surplus[sl],
            window=window,
            soc_init=soc_init,
            charge_budget=E_MAX*(sum(deg[sl])/len(deg[sl]))*(nh/HOURS_PER_DAY),
            PCH_MAX=E_MAX*inputs["C-factor"],
            PDIS_MAX=E_MAX*inputs["C-factor"],
            SOC_MIN=0,
        )

        _solve(model, tee=tee)

        day_result = _extract_results(
            model,
            demand[sl],
            pv_prod[sl],
            eta_dis[sl],
            pv_price[sl],
            grid_price[sl],
            grid_charge_price[sl],
        )
        all_results.append(pd.DataFrame(day_result))

        soc_init = model.SOC[nh - 1]()

    results = pd.concat(all_results, ignore_index=True)
    assert len(results) == T, f"len(results)={len(results)} != T={T}"
    results["Date&Time"] = data["Date&Time"]
    results["BESS Degradation factor"] = deg
    results.to_excel("Best Price Daily.xlsx", index=False)
    return model, results

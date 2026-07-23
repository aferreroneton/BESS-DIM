import pandas as pd
from pyomo.environ import *
from pyomo.environ import SolverFactory
from pyomo.environ import Expression
import numpy as np


#-------AÑADIR PARAMETRO COSTE POR CICLO (O POR kW)


def opt_pv_first(data, inputs):

    #----------------------------------------PARAMETROS----------------------------------------

    #-------------EXÓGENOS-------------
    demand = data["Demand"].tolist()                                                    #Demanda del cliente en MWh con granularidad horaria
    pv_prod = data["PV Generation"].tolist()                                            #Generación de la planta PV en MWh con granularidad horaria
    pv_price = data["Price Charging from Surplus"].tolist()                             #Precio de carga de excedentes en €/MWh con granularidad horaria (merchant o ppa price) --- NO aplica en este escenario
    pv_price_first = [-1]*len(pv_price)                                                 #Para priorizar excedentes PV, se bonificará la carga de PV poniendo la carga -X €/MWh (en este caso -1 para simplificar resolución cuanto más agresivo el beneficio más se disminuirán los excedemtes pero el modelo tardará más en resolver y la solución estará más lejos del óptimo base)
    pot_contratada = data["ContPower (MW)"].tolist()                                    #Potencia contratada por el cliente en cada periodo horario en MW con granularidad horaria
    tolls = inputs.get("tolls", 1)                                                      #Parámetro: {1 si Tolls, 0 si No Tolls}
    grid_price = data["Final Prices"].tolist()                                          #Precio de red en €/MWh con granularidad horaria
    if tolls == 1:
        grid_charge_price = data["Final Prices"].tolist()                               #Si Tolls, precios de red CON peajes en €/MWh con granularidad horaria
    elif tolls == 0:
        grid_charge_price = (data["Final Prices"]-data["Total Grid Costs"]).tolist()    #Si No Tolls, precios de red SIN peajes en €/MWh con granularidad horaria 
    else:
        print("ERROR")
    deg = data["BESS Degradation factor"]                                               #Degradación del BESS según fabricante con granularidad horaria                                     
    eta_ch = 1                                                                          #Eficiencia de carga (1 by default, aún así debería incluirla en el modelo) ---PENDIENTE  
    eta_dis = data["RTE Efficiency"].tolist()                                           #Eficiencia de descarga según fabricante con granularidad horaria

    #-------------ENDÓGENOS-------------
    T = len(data)                                                                       #Scope temporal del modelo en horas
    h = 24                                                                              #horas/días
    days = range (T // h)                                                               #Scope temporal del sistema en días
    discharge_cost = inputs["Discharge Cost"]                                           #Precio de descarga en €/MWh --- TBD para buscar una utilización
    E_max = inputs["N containers"]*inputs["Pot BESS"]                                   #Capacidad máxima nominal del BESS en función de la potencia nominal del BESS y el número de containers en MW
    SOC0 = 0                                                                            #State Of Charge (SOC) inicial
    SOC_min = 0                                                                         #State of Charge (SOC) mínimo
    SOC_max_0 = E_max                                                                   #State Of Charge (SOC) máximo nominal en función de la capacidad máxima nominal del BESS
    Pch_max = inputs["C-factor"]*E_max                                                  #Capacidad máxima de carga en función de la capacidad máxima nominal y el C-Factor en MW
    Pch_min=  0                                                                         #Capacaidad mínima de carga
    Pdis_max = inputs["C-factor"]*E_max                                                 #Capacidad máxima de descarga en función de la capacidad máxima nominal y el C-Factor en MW
    SOC_max_effective = (SOC_max_0 * deg).tolist()                                      #State of Charge (SOC) máximo efectivo en función del SOC máximo nominal y la degracación con granularidad horaria
    max_cycles = len(days)*inputs["Cycles/Day"]                                         #Número máximo de ciclos/día según fabricante
    pv_surplus = [max(pv_prod[t] - demand[t], 0) for t in range(T)]                     #Excedentes PV, solo si la producción es mayor que la demanda

    #----------------------------------------DEFINICIÓN----------------------------------------                                   

    model = ConcreteModel()
    model.T  = RangeSet(0, T-1)

    #----------------------------------------VARIABLES----------------------------------------

    model.Gch = Var(model.T, within=NonNegativeReals, bounds=(0, Pch_max))              #Grid Charge (Carga de red) en t∈T con unidad MWh y limitada por la capacidad máxima de carga del BESS
    model.PVch = Var(model.T, within=NonNegativeReals, bounds=(0, Pch_max))             #PV Charge (Carga de PV) en t∈T con unidad MWh y limitada por la capacidad máxima de carga del BESS
    model.Bdis = Var(model.T, within=NonNegativeReals, bounds=(0, Pdis_max))            #BESS Disharge (Descarga) en t∈T con unidad MWh y limitada por la capacidad máxima de descarga del BESS
    model.u = Var(model.T, within=Binary)                                               #Binaria: {0 si Descarga, 1 si Carga} para t∈T

    def importdemand_bounds(m, t):
        value = demand[t] - pv_prod[t]                                                  #Upper bound para impedir carga +inf (o hasta Pcon) en caso de precios negativos
        upper_bound = value if value > 0 else 0
        return (0, upper_bound)
    model.ImportDemand = Var(model.T, within=NonNegativeReals, bounds=importdemand_bounds)      #Cobertura red en t∈T con unidad MWh y limitada por la demanda después de PV

    def soc_bounds(m, t):
        return (SOC_min, SOC_max_effective[t])                                          #Upper bound dinámico en base al SOC máximo efectivo, con granularidad horaria
    model.SOC = Var(model.T, within=NonNegativeReals, bounds=soc_bounds)                #State Of Charge en t∈T con unidad MW y limitado por la degradación

    #----------------------------------------RESTRICCIONES----------------------------------------

    # Inicialización de la Variable State of Charge (SOC) en base al valor incial del SOC (SOC0) --- No existe SOC[t-1]
    model.soc0 = Constraint(expr=model.SOC[0] == SOC0 + ((model.Gch[0] + model.PVch[0]) - model.Bdis[0]/eta_dis[0]))

    # SOC dinámico con eficiencias variables
    def soc_rest_rule(m, t):
        return m.SOC[t] == m.SOC[t-1] + ((m.Gch[t] + m.PVch[t]) - m.Bdis[t]/eta_dis[t])     # El SOC para toda hora t∈T será el resultado del SOC en t-1 + Cargas en t * eficiencia carga - Descarga en t / eficiencia descarga
    model.soc_rest = Constraint(RangeSet(1, T-1), rule=soc_rest_rule)

    # PVch ≤ excedente
    def pvch_limit_rule(m, t):
        return m.PVch[t] <= pv_surplus[t]                                                   # La carga de PV en t nunca podrá superar los excedentes en t
    model.pvch_limit = Constraint(model.T, rule=pvch_limit_rule)

    # ImportDemand ≥ demanda restante
    def import_lb_rule(m, t):
        return m.ImportDemand[t] >= demand[t] - pv_prod[t] - m.Bdis[t]                      # Ecuación de balanca (Cobertura + PV + Descarga >= Demanda) para todo t∈T
    model.import_lb_cons = Constraint(model.T, rule=import_lb_rule)

    # Pot. Contratada
    def pot_limit(m, t):
        return m.ImportDemand[t] + m.Gch[t] <= pot_contratada[t]                            # El importe neto de energía de red en t (Cobertura + Carga Red) no podrá superar la potencia contratada para ese periodo
    model.pot_limit = Constraint(model.T, rule=pot_limit)

    # No simultaneidad (opcional: mantiene 8760 binarias u)
    def no_simul_chdis_1(m, t):
        return m.Gch[t] + m.PVch[t] <= Pch_max * m.u[t]                                     # Si carga (u=1) la carga total en t no podrá superar la capacidad máxima de carga establecida por el C-Factor; Si Descarga (u=0), la carga total tendrá que ser 0
    model.no_simul_1 = Constraint(model.T, rule=no_simul_chdis_1)
    def no_simul_chdis_2(m, t):
        return m.Bdis[t] <= Pdis_max * (1 - m.u[t])                                         # Si carga (u=1) la descarga total tendrá que ser 0; Si Descarga (u=0), la descarga total en t no podrá superar la capacidad máxima de descarga establecida por el C-Factor 
    model.no_simul_2 = Constraint(model.T, rule=no_simul_chdis_2)

    def ciclos_cap_rule(m):
        return sum(m.Gch[t] + m.PVch[t] for t in m.T) <= max_cycles * (sum(SOC_max_effective[t] for t in m.T) / len(m.T))       # La potencia cargada total en todo el periodo analizado (Σt∈T) no podrá superar la potencia máxima cargada en función del número de ciclos y la capacidad máxima efectvia del BESS
    model.ciclos_cap = Constraint(rule=ciclos_cap_rule)

    #----------------------------------------FUNCIÓN OBJETVIO----------------------------------------

    def obj_rule(m):                                    #MINIMIZAR
        return sum(                                     #COSTE TOTAL = 
            m.ImportDemand[t] * grid_price[t] +         #+ COSTE COBERTURA DE LA DEMANDA POR RED 
            m.Gch[t] * grid_charge_price[t] +           #+ COSTE CARGA RED
            m.PVch[t] * pv_price_first[t] +             #+ COSTE CARGA PV con BENEFICIOS (PARA PRIORIZAR PV)
            m.Bdis[t] * discharge_cost                  #+ COSTE DESCARGA
            for t in m.T                                #PARA Σt∈T
        )
    
    if hasattr(model, 'obj'):
        model.del_component('obj')
    model.obj = Objective(rule=obj_rule, sense=minimize)

    #----------------------------------------SOLVER----------------------------------------

    solver = SolverFactory('cbc')

    #----------------------------------------RESOLUCIÓN----------------------------------------

    res = solver.solve(model, tee=True)

    # print("\nHora | SOC [kWh] | Gch [kW] | PVch [kW] | Bdis [kW] | Import [kW]")
    # for t in model.T:
    #     print(f"{t:2d}   | {model.SOC[t]():6.2f}   | {model.Gch[t]():6.2f}   | {model.PVch[t]():6.2f}   | {model.Bdis[t]():6.2f}   | {model.ImportDemand[t]():6.2f}")

    #----------------------------------------OUTPUTS----------------------------------------

    data_result = {
        "Date&Time"                 :   data["Date&Time"],
        "Demanda"                   :   demand,
        "Producción PV"             :   pv_prod,
        "RTE Efficiency"            :   eta_dis,
        "BESS Degradation factor"   :   data["BESS Degradation factor"],
        "Carga de PV"               :   [model.PVch[t]() for t in model.T],
        "Carga de red"              :   [model.Gch[t]() for t in model.T],
        "Precio Carga PV"           :   pv_price,
        "Precio Carga Red"          :   grid_charge_price,
        "Precio Red"                :   grid_price,
        "SOC"                       :   [model.SOC[t]() for t in model.T],
        "Descarga"                  :   [model.Bdis[t]() for t in model.T],
        "Cobertura red"             :   [model.ImportDemand[t]() for t in model.T],
        "Excedentes"                :   [pv_surplus[t] - model.PVch[t].value for t in model.T]
    }

    results = pd.DataFrame(data_result)

    results.to_excel("PV First.xlsx", index=False)

    return model, results
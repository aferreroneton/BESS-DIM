import pandas as pd
import numpy as np


def _simulate_day(
    demand,
    pv_prod,
    pv_price,
    pot_contratada,
    grid_price,
    grid_charge_price,
    eta_dis,
    soc_max_effective,
    window,
    soc_init,
    PCH_MAX,
    PDIS_MAX,
):
    """
    Replica, hora a hora, la lógica de despacho real de PBI (workflow KNIME
    'IT BESS 2026 dev 24h...knwf', Metanode #152) en vez de resolver un LP.
    No es una optimización conjunta del día: es la misma heurística greedy en
    dos pasadas (carga / descarga) que usa PBI, con el mismo orden de
    prioridad -- por precio, no cronológico -- dentro de cada pasada:

      1. Charging Source (nodo #140): PV si hay excedente Y su precio es <= el
         de red ESA MISMA hora; si no, Red. Nunca compara horas entre sí.
      2. Cap by ContPower from grid (nodo #153): tope de carga desde red =
         ContPower - demanda no cubierta tras autoconsumo directo. Sin precio.
      3. Target CHARGING Volume (nodos #159/#171): presupuesto de MWh a cargar
         en el día -- se dimensiona sobre la demanda no cubierta de las horas
         de DESCARGA (noche) de ese mismo día, no de todo el día completo, y
         se capa además por capacidad efectiva de la batería y por lo máximo
         que darían de sí las horas de la ventana de carga -- calculado ANTES
         de repartir horas. Confirmado empíricamente (ratio Carga/Descarga
         diaria de PBI prácticamente constante, ~1/eficiencia, en 365 días de
         2027 para HaAr10): si se cuenta también la demanda no cubierta de la
         propia ventana de carga (p.ej. la mañana antes de que arranque el
         PV), el presupuesto se infla muy por encima de lo que luego hace
         falta descargar esa misma noche.
      4. Reparto del presupuesto (nodos #173 Rank + #203 Sorter + bucle
         #177/#183): las horas de la ventana de carga se ordenan de MÁS
         BARATA a MÁS CARA (precio de red si la fuente es Red, Pool price si
         es PV) y el presupuesto se va asignando en ESE orden, no en orden
         cronológico, hasta agotarlo o agotar el tope físico de cada hora.
         Es decir: SÍ hay sensibilidad al precio dentro del día -- pero solo
         para decidir el ORDEN de llenado dentro de un presupuesto fijo, no
         para comparar el coste de cargar hoy contra el de otro día (eso
         seguiría exigiendo una optimización multi-día que PBI no hace).
      5. Descarga (nodos #159 'Expensive Demand' + #189 Rank + bucle
         #190/#198): solo se descarga para cubrir horas 'caras' (precio de
         mercado > precio medio de carga disponible ese día), y esas horas se
         atienden de MÁS CARA a MÁS BARATA, hasta agotar un presupuesto de
         descarga ('Dischargeable Storage' = Target CHARGING Volume ajustado
         por eficiencia, nodo #171) o el tope de potencia de descarga/hora.

    No se replica el ajuste de rango +24 que PBI aplica solo a la estrategia
    'PV surplus first' (fuerza PV antes que Red en el reparto pase lo que
    pase con el precio): esta función modela la rama de PBI equivalente a
    'Best price PV vs Grid', que es el caso de estudio de esta comparación.
    """

    T = len(demand)

    pv_direct_sc = [min(demand[t], pv_prod[t]) for t in range(T)]
    unmet_after_direct_sc = [max(demand[t] - pv_prod[t], 0.0) for t in range(T)]
    pv_surplus = [max(pv_prod[t] - demand[t], 0.0) for t in range(T)]
    cap_by_contpower = [max(pot_contratada[t] - unmet_after_direct_sc[t], 0.0) for t in range(T)]

    charging_source = []
    effective_price = []
    potential_charge = []
    for t in range(T):
        is_pv = pv_surplus[t] > 0 and pv_price[t] <= grid_charge_price[t]
        charging_source.append("PV" if is_pv else "Grid")
        effective_price.append(pv_price[t] if is_pv else grid_charge_price[t])

        if window[t] != 1:
            potential_charge.append(0.0)
            continue
        source_limit = min(PCH_MAX, pv_surplus[t]) if is_pv else PCH_MAX
        potential_charge.append(max(min(source_limit, cap_by_contpower[t]), 0.0))

    window_hours = [t for t in range(T) if window[t] == 1]
    night_hours = [t for t in range(T) if window[t] != 1]

    avg_charging_price_available = (
        float(np.mean([effective_price[t] for t in window_hours])) if window_hours else 0.0
    )
    # Solo cuenta la demanda no cubierta de las horas de DESCARGA (noche) -- es lo que
    # de verdad hay que reponer con la carga del dia. Sumar tambien las horas de la
    # propia ventana de carga (p.ej. la manana antes de que arranque el PV) infla el
    # presupuesto muy por encima de lo que luego se va a descargar esa misma noche.
    expensive_demand = [
        unmet_after_direct_sc[t] if (window[t] != 1 and grid_price[t] > avg_charging_price_available) else 0.0
        for t in range(T)
    ]
    eff_factor_day = float(np.mean(eta_dis)) if len(eta_dis) else 1.0
    max_charging_volume = sum(expensive_demand) / eff_factor_day if eff_factor_day > 0 else 0.0
    bess_effective_capacity_day = float(np.mean(soc_max_effective)) if len(soc_max_effective) else 0.0
    max_potential_charge_from_source = sum(potential_charge[t] for t in window_hours)

    target_charging_volume = max(
        min(max_charging_volume, bess_effective_capacity_day, max_potential_charge_from_source), 0.0
    )
    dischargeable_storage = target_charging_volume * eff_factor_day

    # Reparto de CARGA: de más barata a más cara segun el precio de DECISION de esa hora
    # (Effective Charging Price -- pv_price si la fuente es PV, grid_charge_price si es
    # Red -- nodo #175, rama "Effective Charging Price + HourOfWindow/10000"), con la
    # hora del dia como desempate. En modo Free (pv_price=0) esto colapsa a orden
    # CRONOLOGICO entre las horas con excedente PV: todas empatan a precio 0, así que se
    # reparte por la propia hora -- confirmado con datos reales (dia 11 enero, HaAr10):
    # PBI carga el excedente completo en las primeras horas con sol (10h, 11h) y va
    # recortando/cerrando el grifo segun se acaba el presupuesto del dia, en vez de
    # priorizar la hora de Pool price mas barato.
    #
    # El precio se redondea a 1 decimal antes de rankear: confirmado con datos reales de
    # Tudela (modo Merch, pv_price = Pool price, con valores reales por hora -- no 0 fijo
    # como en Free). El 7 de noviembre, PBI carga las horas 10/11/12 (consecutivas) y dejó
    # sin usar 13/14 pese a que su Pool price era CASI IDENTICO (-0,17/-0,16/-0,16/-0,17/
    # -0,18 €/MWh, diferencias de centimos) -- si se rankea por el precio exacto sin
    # redondear, esos centimos de ruido deciden el orden y el resultado no coincide; si se
    # redondea antes de rankear, esas horas quedan EMPATADAS y el desempate por hora
    # reproduce exactamente lo que hace PBI.
    #
    # OJO: redondear al ENTERO (como se hizo al principio) es demasiado grosero para Red --
    # confirmado con HaAr10 (16 enero): fusionaba en un mismo "empate" horas con precios de
    # decision REALMENTE distintos (72,60 y 73,44 €/MWh, un salto real de 0,84 €/MWh, no
    # ruido), invirtiendo el orden real (PBI carga primero la mas barata de las dos). A 1
    # decimal, el ruido de Tudela (centesimas) sigue empatando, pero un salto de varias
    # decimas o mas en Red ya no se confunde con ruido.
    adjusted_charging_price = {
        t: round(effective_price[t], 1) + t / 10000.0
        for t in window_hours
    }
    charge_order = sorted(window_hours, key=lambda t: adjusted_charging_price[t])

    pv_ch = [0.0] * T
    grid_ch = [0.0] * T
    remaining_budget = target_charging_volume
    for t in charge_order:
        charge_mwh = max(min(remaining_budget, potential_charge[t]), 0.0)
        remaining_budget -= charge_mwh
        if charging_source[t] == "PV":
            pv_ch[t] = charge_mwh
        else:
            grid_ch[t] = charge_mwh

    # Reparto de DESCARGA: de más cara a más barata (nodos #189/#198), solo
    # horas 'caras', no cronológico.
    discharge_order = sorted(night_hours, key=lambda t: grid_price[t], reverse=True)

    discharge = [0.0] * T
    remaining_storage = dischargeable_storage
    for t in discharge_order:
        dis_mwh = max(min(remaining_storage, expensive_demand[t], PDIS_MAX), 0.0)
        discharge[t] = dis_mwh
        remaining_storage -= dis_mwh

    # SOC: se reconstruye en orden CRONOLÓGICO a partir de lo que decidieron
    # los repartos anteriores (el balance de energía es, por naturaleza,
    # secuencial en el tiempo, aunque la decisión de qué horas usar no lo sea).
    # Se recorta de forma defensiva a [0, capacidad efectiva] -- no debería
    # hacer falta si los presupuestos están bien calculados, pero evita que un
    # caso límite (p. ej. arrastre de un día anterior) produzca un SOC físicamente
    # imposible.
    soc = [0.0] * T
    soc_prev = soc_init
    for t in range(T):
        soc_t = soc_prev + (pv_ch[t] + grid_ch[t]) - (discharge[t] / eta_dis[t] if eta_dis[t] > 0 else 0.0)
        soc_t = min(max(soc_t, 0.0), soc_max_effective[t])
        soc[t] = soc_t
        soc_prev = soc_t

    import_demand = [max(demand[t] - pv_prod[t] - discharge[t], 0.0) for t in range(T)]

    return {
        "Demanda"                       :   demand,
        "Producción PV"                 :   pv_prod,
        "RTE Efficiency"                :   eta_dis,
        "Carga de PV"                   :   pv_ch,
        "Carga de red"                  :   grid_ch,
        "Precio Carga PV"               :   pv_price,
        "Precio Carga Red"              :   grid_charge_price,
        "Precio Red"                    :   grid_price,
        "SOC"                           :   soc,
        "Descarga"                      :   discharge,
        "Cobertura red"                 :   import_demand,
    }, soc[-1] if T > 0 else soc_init


def opt_pbi_logic_daily(data, inputs, tee=False):
    """
    Resuelve el año iterando día a día (bloques de 24h), replicando la lógica
    de despacho REAL de PBI (heurística secuencial greedy con reparto por
    precio, tomada del workflow KNIME) en vez de un LP de coste mínimo. No hay
    solver: es una simulación determinista pensada para comparar contra
    'Best price PV vs Grid' y 'PV surplus first' (ambos LP) con el mismo
    pipeline de datos/KPIs del dashboard.

    Devuelve (None, results) -- no hay 'model' porque no se resuelve ningún
    MILP; el llamador (dimBESS.solve_scenario) solo usa 'results'.
    """

    HOURS_PER_DAY = 24
    E_MAX = inputs["Pot BESS"] * inputs["N containers"] * inputs["DoD %"]

    demand = (data["Power demand kWh"] / 1000).tolist()
    pv_prod = (data["PV Generation kWh"] / 1000).tolist()
    pot_contratada = data["Cont Power MW"].tolist()
    grid_price = data["Final Prices"].tolist()
    pv_price_mode = inputs["PPA Mode"]
    if pv_price_mode == "Free":
        pv_price = [0.0] * len(demand)
    elif pv_price_mode == "PPA fixed price":
        pv_price = [inputs["PPA Price"]] * len(demand)
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

    # Igual que en best_price_daily/pv_first_daily: el coste reportado de carga
    # de red va siempre sin tolls, independientemente de 'tolls' (que solo rige
    # el precio de DECISIÓN -- aquí, la comparación PV vs Red de cada hora).
    grid_charge_price_notolls = (data["Final Prices"] - data["Tolls and RC"]).tolist()

    T = len(demand)
    if T % HOURS_PER_DAY != 0:
        raise ValueError(f"T={T} no es múltiplo de {HOURS_PER_DAY}")

    pv_surplus_full = [max(pv_prod[t] - demand[t], 0) for t in range(T)]

    PCH_MAX = E_MAX * inputs["C-factor"]
    PDIS_MAX = E_MAX * inputs["C-factor"]

    n_days = T // HOURS_PER_DAY
    soc_init = 0.0
    all_results = []

    for d in range(n_days):
        start = d * HOURS_PER_DAY
        sl = slice(start, start + HOURS_PER_DAY)

        # Ventana estructural día=carga / tarde-noche=descarga (proxy de
        # 'Charging max hour' / 'Latest SURPLUS hour' de PBI). El suelo fijo es
        # la hora t=15 (15:00) -- comprobado con datos reales de PBI (HaAr10,
        # 365 días): carga desde red después de las 15:00 solo en 7/365 días, y
        # en los 7 hay excedente de PV en alguna hora posterior ESE MISMO día
        # (aunque esa hora en concreto tenga excedente 0) -- es decir, la
        # ventana se alarga porque el PV vuelve a aparecer más tarde, no por
        # una hora fija distinta para Red. No hace falta tratar Red y PV con
        # ventanas separadas: basta que el suelo del "max(...)" sea 15, no 16.
        pv_day = np.array(pv_surplus_full[sl])
        idx = np.where(pv_day > 0)[0]
        last_pv = idx[-1] if len(idx) > 0 else -1
        t_end = min(max(15, last_pv), HOURS_PER_DAY - 1)
        window = np.zeros(HOURS_PER_DAY)
        window[:t_end + 1] = 1

        day_result, soc_init = _simulate_day(
            demand=demand[sl],
            pv_prod=pv_prod[sl],
            pv_price=pv_price[sl],
            pot_contratada=pot_contratada[sl],
            grid_price=grid_price[sl],
            grid_charge_price=grid_charge_price[sl],
            eta_dis=eta_dis[sl],
            soc_max_effective=soc_max_effective[sl],
            window=window,
            soc_init=soc_init,
            PCH_MAX=PCH_MAX,
            PDIS_MAX=PDIS_MAX,
        )
        day_result["Precio Carga Red sin Tolls"] = grid_charge_price_notolls[sl]
        all_results.append(pd.DataFrame(day_result))

    results = pd.concat(all_results, ignore_index=True)
    assert len(results) == T, f"len(results)={len(results)} != T={T}"
    results["Date&Time"] = data["Date&Time"].values
    results["BESS Degradation factor"] = deg.values
    return None, results

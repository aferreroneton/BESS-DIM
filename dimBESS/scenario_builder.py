"""
Réplica en Python de la lógica de la hoja 'Scenarios' del Excel de inputs,
para poder definir escenarios directamente (ej. desde un dashboard) sin
depender de editar esa hoja.

Las fórmulas originales de Excel (por fila de escenario, en la hoja Scenarios):

    Nominal Capacity   = IF(Type=Solax Trene, 1.044, IF(Type=Risen+mg, 5.016))
    Battery size MWh   = Nominal Capacity * N containers
    DoD %              = IF(Type=Solax Trene, 0.95, IF(Type=Risen+mg, 1.0))
    Battery op. cap.   = DoD % * Battery size MWh
    Charge/Discharge   = Battery op. cap. * C-Factor
    Leasing Scenario   = IF(Type=Solax Trene, "Solax Trene",
                          IF(Type=Risen+mg, IF(N<4, "Risen+mg 10%Dto", "Risen+mg big order")))
    € Leasing Monthly  = INDEX/MATCH en la hoja Leasing por (Leasing Scenario, Client Rating)
    Scenario (nombre)  = Client & "_" & Plant & "_" & Type & "_" & N & "Container_" & Battery size & "MWh_" & Price mode
"""

import dimBESS

CONTAINER_TYPES = ["Solax Trene", "Risen+mg"]

CONTAINER_NOMINAL_CAPACITY = {
    "Solax Trene"   :   1.044,
    "Risen+mg"      :   5.016,
}

CONTAINER_DOD = {
    "Solax Trene"   :   0.95,
    "Risen+mg"      :   1.0,
}

PRICE_MODES = ["Free", "PPA fixed price", "Merch compensation"]

SURPLUS_STRATEGIES = sorted(dimBESS.SUPPORTED_SURPLUS_STRATEGIES)

# Leasing!D3:I5 ("Full fee / Sin Subvención"), la única franja que usa hoy la fórmula de Excel
LEASING_TABLE = {
    "Risen+mg big order"   :   {5: 8655, 6: 8525, 7: 8400, 8: 8275, 9: 8155, 10: 8155},
    "Risen+mg 10%Dto"      :   {5: 8825, 6: 8695, 7: 8565, 8: 8440, 9: 8315, 10: 8315},
    "Solax Trene"          :   {5: 2345, 6: 2310, 7: 2280, 8: 2245, 9: 2210, 10: 2210},
}

CLIENT_RATING_MIN = min(next(iter(LEASING_TABLE.values())).keys())
CLIENT_RATING_MAX = max(next(iter(LEASING_TABLE.values())).keys())


def leasing_scenario_for(container_type, n_containers):
    if container_type == "Solax Trene":
        return "Solax Trene"
    if container_type == "Risen+mg":
        return "Risen+mg 10%Dto" if n_containers < 4 else "Risen+mg big order"
    raise ValueError(f"Type of Container desconocido: {container_type}")


def leasing_monthly_fee(leasing_scenario, client_rating):
    try:
        return LEASING_TABLE[leasing_scenario][int(client_rating)]
    except KeyError:
        raise ValueError(
            f"No hay tarifa de leasing para Client Rating={client_rating} "
            f"(rango soportado: {CLIENT_RATING_MIN}-{CLIENT_RATING_MAX})"
        )


def build_scenario(
    client,
    plant,
    tariff,
    container_type,
    n_containers,
    client_rating,
    cycles_day,
    c_factor,
    surplus_strategy,
    price_mode,
    ppa_price,
    original_ppa_price,
    discharge_cost=0.0,
    tolls=1,
    study_type="Base study",
):
    """Construye un dict de escenario con el mismo esquema que dimBESS.load_scenarios()."""

    if container_type not in CONTAINER_NOMINAL_CAPACITY:
        raise ValueError(f"Type of Container desconocido: {container_type}")
    if surplus_strategy not in dimBESS.SUPPORTED_SURPLUS_STRATEGIES:
        raise ValueError(f"Surplus Strategy desconocida: {surplus_strategy}")
    if study_type not in dimBESS.SUPPORTED_STUDY_TYPES:
        raise ValueError(f"Study Type desconocido: {study_type}")

    nominal_capacity = CONTAINER_NOMINAL_CAPACITY[container_type]
    dod = CONTAINER_DOD[container_type]
    battery_size_mwh = nominal_capacity * n_containers
    battery_op_capacity = dod * battery_size_mwh
    charge_discharge_per_hour = battery_op_capacity * c_factor

    leasing_scenario = leasing_scenario_for(container_type, n_containers)
    leasing_monthly = leasing_monthly_fee(leasing_scenario, client_rating)

    provider = "Solax" if "solax" in container_type.lower() else "Risen"

    battery_size_label = f"{battery_size_mwh:.3f}".replace(".", ",")
    scenario_name = f"{client}_{plant}_{container_type}_{n_containers}Container_{battery_size_label}MWh_{price_mode}"

    ppa_imp = float(ppa_price) - float(original_ppa_price)

    return {
        "Scenario"                          :   scenario_name,
        "Container Type"                    :   container_type,
        "Provider"                          :   provider,
        "Nominal Capacity"                  :   nominal_capacity,
        "N Containers"                      :   float(n_containers),
        "C-Factor"                          :   float(c_factor),
        "Tariff"                            :   tariff,
        "PPA Mode"                          :   price_mode,
        "Surplus Strategy"                  :   surplus_strategy,
        "PPA Price"                         :   float(ppa_price),
        "PPA Improvement"                   :   ppa_imp,
        "Discharge Cost"                    :   float(discharge_cost),
        "Cycles/Day"                        :   float(cycles_day),
        "tolls"                             :   tolls,
        "€ Leasing Monthly"                 :   float(leasing_monthly),
        "Study Type"                        :   study_type,
        # Campos informativos (no consumidos por solve_scenario, pero mostrados en el builder
        # para replicar 1:1 lo que se ve en la hoja Scenarios):
        "Client Rating"                     :   client_rating,
        "Battery size MWh"                  :   battery_size_mwh,
        "Depth of Discharge (DoD) %"        :   dod,
        "Battery operational capacity MWh"  :   battery_op_capacity,
        "Charge capacity per hour MWh"      :   charge_discharge_per_hour,
        "Discharge capacity per hour MWh"   :   charge_discharge_per_hour,
        "Leasing Scenario"                  :   leasing_scenario,
    }

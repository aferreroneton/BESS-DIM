import pandas as pd
import numpy as np

def pv_extension(base, is_leap):

    feb_gen = (base[base["Month num"]==2]).set_index("Date&Time")["PV Generation kWh"]
    feb_gen_joker = feb_gen.groupby(feb_gen.index.hour).median()

    pv_base = [base["PV Generation kWh"].reset_index(drop=True)][0]

    if not is_leap:
        pv_year = pv_base
    else:
        feb28_end = 59*24
        pv_leap = pd.concat([pv_base.iloc[:feb28_end], feb_gen_joker.reset_index(drop=True), pv_base.iloc[feb28_end:]], ignore_index=True)
        pv_year = pv_leap

    return pv_year

def demand_extension(base, index_df, y1):

    demand_joker = base.groupby(["Month num", "Weekday", "HourOfDay"])["Power demand kWh"].mean()
    demand_joker_lookup = demand_joker.to_dict()
    demand_lookup = base.set_index(["Date", "HourOfDay"])["Power demand kWh"].to_dict()
    weekday_lookup = ((base.set_index(["Month num", "Day"]))["Weekday"].to_dict())


    aux = index_df.copy()
    aux["Power demand kWh - Joker"] = [demand_joker_lookup[(m, w, h)] for m, w, h in zip(aux["Month num"], aux["Weekday"], aux["HourOfDay"])]
    aux["Ref Weekday"] = [weekday_lookup.get((m, d), np.nan) for m, d in zip(aux["Month num"], aux["Day"])]
    aux["Ref Weekday"] = aux["Ref Weekday"].astype("Int64")
    aux["Delta Days"] = aux["Ref Weekday"] - aux["Weekday"]
    aux["Lag Days"] = aux["Delta Days"].where(aux["Delta Days"] > 0, aux["Delta Days"] + 7)
    aux["Lag Days"] = aux["Lag Days"].astype("Int64")
    aux["Lag Mode"] = pd.NA
    aux.loc[aux["Lag Days"].notna(), "Lag Mode"] = np.where(aux.loc[aux["Lag Days"].notna(), "Lag Days"] <= 3, "negative", "positive")
    aux["Ref DoM Lookup"] = pd.NA
    aux.loc[aux["Lag Mode"] == "positive", "Ref DoM Lookup"] = (aux.loc[aux["Lag Mode"] == "positive", "Day"] + (7 - aux.loc[aux["Lag Mode"] == "positive", "Lag Days"]))
    aux.loc[aux["Lag Mode"] == "negative", "Ref DoM Lookup"] = (aux.loc[aux["Lag Mode"] == "negative", "Day"] - aux.loc[aux["Lag Mode"] == "negative", "Lag Days"])
    aux["Ref Date"] = pd.NaT
    aux.loc[aux["Ref DoM Lookup"].notna(), "Ref Date"] = pd.to_datetime((str(y1)+"-"+aux.loc[aux["Ref DoM Lookup"].notna(), "Month num"].astype(str).str.zfill(2)+"-"+aux.loc[aux["Ref DoM Lookup"].notna(), "Ref DoM Lookup"].astype(str).str.zfill(2)), format="%Y-%m-%d", errors="coerce").dt.date
    aux["Ref Date"] = pd.to_datetime(aux["Ref Date"]).dt.date
    aux["Ref Demand"] = [demand_lookup.get((d, h), np.nan) if pd.notna(d) else np.nan for d, h in zip(aux["Ref Date"], aux["HourOfDay"])]        

    return aux["Ref Demand"].fillna(aux["Power demand kWh - Joker"])

def deg(index_df, curves_risen, curves_solax):

    rte_lookup = curves_risen.set_index("Operation year")["BESS RTE Efficiency"].to_dict()
    risen_bess_lookup = curves_risen.set_index("Operation year")["BESS Degradation"].to_dict()
    solax_bess_lookup = curves_solax.set_index("Operation year")["BESS Degradation"].to_dict()
    # "PV Degradation" es la misma curva en ambas hojas (paneles físicos, no depende del
    # proveedor de contenedor BESS); se toma de curves_risen igual que BESS RTE Efficiency.
    pv_lookup = curves_risen.set_index("Operation year")["PV Degradation"].to_dict()

    aux = index_df.copy()
    aux["Days in Year"] = np.where(pd.to_datetime(aux["Date"]).dt.is_leap_year, 366, 365)

    rte_eff = (aux["Year num"].map(rte_lookup) - (aux["Year num"].map(rte_lookup) - (aux["Year num"] + 1).map(rte_lookup))/aux["Days in Year"]*(aux["Day of Year"]))
    risen_deg = (aux["Year num"].map(risen_bess_lookup) - (aux["Year num"].map(risen_bess_lookup) - (aux["Year num"] + 1).map(risen_bess_lookup))/aux["Days in Year"]*(aux["Day of Year"]))
    solax_deg = (aux["Year num"].map(solax_bess_lookup) - (aux["Year num"].map(solax_bess_lookup) - (aux["Year num"] + 1).map(solax_bess_lookup))/aux["Days in Year"]*(aux["Day of Year"]))
    pv_deg = (aux["Year num"].map(pv_lookup) - (aux["Year num"].map(pv_lookup) - (aux["Year num"] + 1).map(pv_lookup))/aux["Days in Year"]*(aux["Day of Year"]))

    return rte_eff, risen_deg, solax_deg, pv_deg

def mwh_extension(data, periods, prices, curves_risen, curves_solax, y1, years):

    """
    Para la extensión de la generación se asume un perfil de producción constante con independencia
    del día de la semana.
    """

    base = data[["Date&Time", "Date", "Month num", "Day", "Day of Year", "HourOfDay", "Weekday", "PV Generation kWh", "Power demand kWh"]].copy()

    period_lookup = (periods.set_index("Month").stack().to_dict())

    years_list = [y1 + i for i in range(21)]

    data_by_year = {}

    for year in years:

        i = year - 1

        index = pd.date_range(start=f"{years_list[i]}-01-01 00:00:00", end=f"{years_list[i]}-12-31 23:00:00", freq="h")
        is_leap = len(index) == 8784
        index_df = pd.DataFrame({
            "Date&Time"     :   index,
            "Date"          :   index.date,
            "Year"          :   index.year,
            "Year num"      :   year,
            "Month num"     :   index.month,
            "Day"           :   index.day,
            "Day of Year"   :   index.dayofyear,
            "HourOfDay"     :   index.hour + 1,
            "Weekday"       :   ((index.dayofweek + 1) % 7) + 1,
            "Weekday name"  :   index.day_name()
        })

        mask = (index_df["Weekday"] > 1) & (index_df["Weekday"] < 7)
        index_df["Period"] = "P6"
        index_df.loc[mask, "Period"] = [period_lookup[(m, h)] for m, h in zip(index_df.loc[mask, "Month num"], index_df.loc[mask, "HourOfDay"])]
        rte_eff, risen_deg, solax_deg, pv_deg = deg(index_df, curves_risen, curves_solax)

        data_year = index_df.copy()
        data_year["PV Generation kWh"] = pv_extension(base, is_leap)*pv_deg
        data_year["Power demand kWh"] = demand_extension(base, index_df, y1)
        data_year["AC kWh"] = np.minimum(data_year["PV Generation kWh"], data_year["Power demand kWh"])
        data_year = data_year.merge(prices, on="Date&Time", how="left")
        data_year["RTE Efficiency"] = rte_eff
        data_year["BESS Degradation factor - Risen"] = risen_deg
        data_year["BESS Degradation factor - Solax"] = solax_deg

        data_by_year[year] = data_year

    return data_by_year
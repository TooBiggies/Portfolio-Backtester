

import numpy as np
import pandas as pd
import os
import sys
import matplotlib.pyplot as plt
from classes import portfolio_evo

# Allocazione di reference:
# Index 1  # Index 2 # Index 3 # Index 4 ...
#             VTSIM SPYSIM  VXUSSIM GLDSIM  CASHX SHYSIM  IEFSIM  TLTSIM  ZROZSIM KMLMSIM DBMFSIM

initial_w = [ 0.6,  0,      0,      0.05,   0,    0,      0,      0,      0.25,   0.05,   0.05]
imported_dataframe= pd.read_csv("./Timeseries.csv", sep = ";")
# Converte la colonna Date in datetime
imported_dataframe["Date"] = pd.to_datetime(imported_dataframe["Date"], dayfirst=True, errors="coerce")
# Tieni solo le righe con Date >= cutoff
imported_dataframe = imported_dataframe[(imported_dataframe["Date"]>=pd.to_datetime("2000-01-03"))].copy()
imported_dataframe = imported_dataframe[(imported_dataframe["Date"]<=pd.to_datetime("2025-09-04"))].copy().reset_index(drop=True)
#print(imported_dataframe)

ptf = portfolio_evo(initial_balance = 1000.0,
                transac_cost_rate= 0.0029, #0.19% commissioni + 0.1% spread
                exp_rate=0.002,            #0.2% imposta di bollo + 0% tracking error
                tax_rate = 0.26,           #26% conservativo
                rebalance_threshold = 0.1,
                initial_w = initial_w,
                imported_dataframe= imported_dataframe,
                start_date="2019-10-31",
                end_date="2025-10-31",
                stock_price_normalization= True)

df_log       = pd.DataFrame(index = ptf.date)
df_log_delta = pd.DataFrame(index = ptf.date)

#print("Loop in")

for i in ptf.StockPrice.index:
    ptf.reset_tax_transaccost()
    ptf.reset_delta_notional()
    
    StockPrice = ptf.StockPrice.loc[i,:]
    ptf.update_AssetValue_weight(StockPrice)
    
    if ptf.check_rebalance():
        #print(i)
        #print(f"check_rebalance {ptf.check_rebalance()}")
        #print(f"StockPrice\n {StockPrice}")
        ptf.update_notional_tax_transaccost(StockPrice)

    ptf.update_Return(StockPrice)    
    ptf.update_TotValue(StockPrice)    
    ptf.update_NetTotValue(StockPrice)

    df_log.loc[ptf.date[i], "Return"]                = ptf.PercReturn
    df_log.loc[ptf.date[i], "Compound Return"]       = ptf.CompoundReturn
    df_log.loc[ptf.date[i], "TotValue"]              = ptf.TotValue
    df_log.loc[ptf.date[i], "Taxes"]                 = ptf.tax
    df_log.loc[ptf.date[i], "TransacCost"]           = ptf.TransactionalCost
    df_log.loc[ptf.date[i], ptf.IndexName]           = ptf.AssetValue
    df_log_delta.loc[ptf.date[i], ptf.IndexName]     = ptf.delta_notional*StockPrice

#df_log.to_csv("test_output.csv", index=True) # uncomment only if bugs are found and you need to update the reference output for testing
ref_df_log = pd.read_csv("test_output.csv", index_col=0, parse_dates=True)

pd.testing.assert_frame_equal(ref_df_log, df_log, check_dtype=False)

df_log.to_excel("test_output.xlsx")

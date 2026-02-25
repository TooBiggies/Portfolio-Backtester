import sys
import os
# ensure repo root is on sys.path so local modules import correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from classes import portfolio_evo
import backtester_config as cfg

imported_dataframe = pd.read_csv('./Timeseries.csv', sep=';')
imported_dataframe['Date'] = pd.to_datetime(imported_dataframe['Date'], dayfirst=True, errors='coerce')
imported_dataframe = imported_dataframe[(imported_dataframe['Date']>=pd.to_datetime('2000-01-03'))].copy()
imported_dataframe = imported_dataframe[(imported_dataframe['Date']<=pd.to_datetime('2025-09-04'))].copy().reset_index(drop=True)

def backtest(initial_balance, start_date, end_date, initial_w):
    ## RUN PRINCIPALE ##
    # Allocazione su indici di portafoglio:
    # Index 1  # Index 2 # Index 3 # Index 4 ...
    # VTSIM SPYSIM  VXUSSIM GLDSIM  CASHX SHYSIM  IEFSIM  TLTSIM  ZROZSIM KMLMSIM DBMFSIM

    if np.sum(initial_w) != 1:
        print("L'allocazione non somma a 1")
        sys.exit()

    ptf = portfolio_evo(initial_balance = initial_balance,
                    transac_cost_rate= 0.0029, #0.19% commissioni + 0.1% spread
                    exp_rate=0.002,            #0.2% imposta di bollo + 0% tracking error
                    tax_rate = 0.26,           #26% conservativo
                    rebalance_threshold = 0.1,
                    initial_w = initial_w,
                    imported_dataframe= imported_dataframe,
                    start_date = start_date,
                    end_date = end_date,
                    stock_price_normalization= True)

    df_log       = pd.DataFrame(index = ptf.date)
    df_log_delta = pd.DataFrame(index = ptf.date)

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

    df_log.to_excel("output_ptf.xlsx")
    df_log_delta.to_excel("output_ptf_delta.xlsx")

    print(f"Orizzonte temporale   {min(ptf.date).date()} / {max(ptf.date).date()}")
    print(f"Anni in simulazione   {round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)}")
    print(f"CAGR                  {(ptf.CompoundReturn**(1/(round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2))) -1) * 100:.2f}%")
    print(f"Total compound return {ptf.CompoundReturn * 100:.2f}%")
    print(f"Capitale iniziale {ptf.StartValue}") #20260131 vincemauro
    print(f"Capitale finale {ptf.TotValue:.2f}") #20260131 vincemauro
    plt.semilogy(df_log.index,df_log['Compound Return'])
    plt.xlabel('Data')
    plt.ylabel('Compound Return %')
    #plt.title('Grafico')
    #plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

backtest(cfg.CAPITAL, pd.to_datetime(cfg.START_DATE), pd.to_datetime(cfg.END_DATE), cfg.INITIAL_WEIGHTS)

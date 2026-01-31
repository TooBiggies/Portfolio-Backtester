import numpy as np
import pandas as pd
import os
import sys
import matplotlib.pyplot as plt

class portfolio:

    #20260131 vincemauro reimpostati tutti i valori numerici con virgola per forzare il type a float. Diversamente sono int e alla prima assegnazione con virgola si va in errore.
    colonne_escluse = ["Date"]  # colonne da escludere nell'import del DF nell'oggetto

    def __init__(self, initial_balance, transac_cost_rate, tax_rate, exp_rate, rebalance_threshold,
                 initial_w, imported_dataframe, stock_price_normalization = True):
        self.StartValue               = initial_balance         # Valore iniziale del PTF - vincemauro 20260131
        self.TotValue                 = initial_balance         # Valore totale del PTF
        self.NetTotValue              = self.TotValue           # Valore totale del PTF sottraendo  tasse e costi di transazione
        self.transactional_cost_rate  = transac_cost_rate       # Percentuale costi di transazione come somma %commissioni e %spread
        self.TransactionalCost        = 0.0                     # Inizializzazione costo di transazione progressivo
        self.tax_rate                 = tax_rate                # Percentuale tassazione plusvalenza
        self.exp_rate                 = exp_rate                # Tasso spesa annuo in cui inserire la somma di tracking error + 0.2% di imposta di bollo sul dossier titoli
        self.tax                      = 0.0                     # Inizializzazione tassazione progressiva
        self.rebalance_threshold      = rebalance_threshold     # Soglia per effettuare il ribilanciamento dei pesi

        self.df                       = imported_dataframe      # DataFrame di input

        self.IndexName         = [                              # Set dei nomi degli asset in PTF
            col for col in self.df.columns
            if col not in self.colonne_escluse
        ]

        if stock_price_normalization:                                                       # Inizializzazione prezzi degli asset (via normalizzazione o non)
            self.StockPrice = self.df.loc[:,self.IndexName]/self.df.loc[0,self.IndexName]
        else:
            self.StockPrice = self.df.loc[:,self.IndexName]

        self.date                = pd.to_datetime(self.df['Date'], format = '%d/%m/%Y')     # Date della serie storica
        self.initial_w           = pd.Series(data = initial_w, index = self.IndexName)      # Setting pesi teorici (valori da mantenere in PTF)
        self.w                   = self.initial_w                                           # Inizializzazione dei pesi effettivi
        self.delta_notional      = 0.0
        self.AssetValue          = self.TotValue*self.w                                     # Inizializzazione valore degli asset in PTF
        self.PMC                 = self.StockPrice.loc[0,:]                                 # Inizializzazione Prezzo Medio di Carico
        self.PMC_weight          = pd.Series(data = 1.0, index = self.IndexName)            # Inizializzazione denominatore media pesata per calcolo PMC
        self.notional            = self.AssetValue/self.StockPrice.loc[0,:]                 # Inizializzazione notional degli asset
        self.PercReturn          = 0.0                                                      # Inizializzazione rendimenti percentuali
        self.CompoundReturn      = 1.0                                                      # Inizializzazione rendimenti composti

    def update_TotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        self.TotValue = self.calculate_TotValue(StockPrice)

    # def update_AssetValue(self, StockPrice):
    #     #StockPrice deve essere una Series col nome degli Stock come indici
    #     self.AssetValue = self.calculate_AssetValue(StockPrice)

    def update_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        self.NetTotValue = self.calculate_NetTotValue(StockPrice)

    def update_AssetValue_weight(self,StockPrice):
        self.AssetValue = self.notional * StockPrice
        self.w = self.AssetValue/self.calculate_TotValue(StockPrice)

    def calculate_TotValue(self,StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        return self.notional.dot(StockPrice)

    def calculate_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        return self.calculate_TotValue(StockPrice) + self.TransactionalCost + self.tax

    # def calculate_AssetValue(self, StockPrice):
    #     return self.notional * StockPrice

    def update_Return(self, StockPrice):
        old_NetTotValue = self.NetTotValue
        current_NetTotValue = self.calculate_NetTotValue(StockPrice)
        self.PercReturn = current_NetTotValue/old_NetTotValue - 1.0
        self.CompoundReturn *= 1.0 + self.PercReturn

    def update_PMC(self,StockPrice):
        mask_buy = self.delta_notional > 0
        self.PMC = self.PMC.copy() #?
        self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                              + (self.delta_notional*StockPrice)[mask_buy] )
        #print("Debug 1")
        #print(f"self.PMC_weight[mask_buy] {self.PMC_weight[mask_buy]}")
        #print(f"self.delta_notional[mask_buy] {self.delta_notional[mask_buy]}")
        self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
        #print("Debug 2")
        self.PMC[mask_buy] /= self.PMC_weight[mask_buy]
        #print("Debug 3")

    def update_tax(self,StockPrice):
        mask_tax = (self.delta_notional < 0) & (StockPrice > self.PMC)
        if np.sum(mask_tax) >0:
            self.tax = (self.delta_notional*StockPrice)[mask_tax].sum()*self.tax_rate
        else:
            self.tax = 0.0

    def update_transactional_cost(self, StockPrice):
        self.TransactionalCost = -(abs(self.delta_notional)*StockPrice).sum()*self.transactional_cost_rate

    def update_notional_tax_transaccost(self, StockPrice):
        self.delta_notional = (self.initial_w - self.w)*self.calculate_TotValue(StockPrice)/StockPrice
        self.update_PMC(StockPrice)
        self.update_tax(StockPrice)
        self.update_transactional_cost(StockPrice)
        self.notional += self.delta_notional

    def reset_tax_transaccost(self):
        self.tax = 0.0
        self.TransactionalCost = 0.0

    def reset_delta_notional(self):
        self.delta_notional = 0.0

    def check_rebalance(self):
        if sum( np.abs(self.w - self.initial_w) > self.rebalance_threshold) > 0:
            return True
        else:
            return False
        

class portfolio_evo: #20260131 vincemauro

    #20260131 vincemauro reimpostati tutti i valori numerici con virgola per forzare il type a float. Diversamente sono int e alla prima assegnazione con virgola si va in errore.
    colonne_escluse = ["Date"]  # colonne da escludere nell'import del DF nell'oggetto

    def __init__(self, initial_balance, transac_cost_rate, tax_rate, exp_rate, rebalance_threshold,
                 initial_w, imported_dataframe, start_date, end_date, stock_price_normalization = True):
        self.StartValue               = initial_balance         # Valore iniziale del PTF - vincemauro 20260131
        self.TotValue                 = initial_balance         # Valore totale del PTF
        self.NetTotValue              = self.TotValue           # Valore totale del PTF sottraendo  tasse e costi di transazione
        self.transactional_cost_rate  = transac_cost_rate       # Percentuale costi di transazione come somma %commissioni e %spread
        self.TransactionalCost        = 0.0                     # Inizializzazione costo di transazione progressivo
        self.tax_rate                 = tax_rate                # Percentuale tassazione plusvalenza
        self.exp_rate                 = exp_rate                # Tasso spesa annuo in cui inserire la somma di tracking error + 0.2% di imposta di bollo sul dossier titoli
        self.tax                      = 0.0                     # Inizializzazione tassazione progressiva
        self.rebalance_threshold      = rebalance_threshold     # Soglia per effettuare il ribilanciamento dei pesi

        self.df                       = imported_dataframe[(imported_dataframe["Date"]>=pd.to_datetime(start_date))].copy()
        self.df                       = self.df[(self.df["Date"]<=pd.to_datetime(end_date))].copy().reset_index(drop=True)

        self.IndexName         = [                              # Set dei nomi degli asset in PTF
            col for col in self.df.columns
            if col not in self.colonne_escluse
        ]

        if stock_price_normalization:                                                       # Inizializzazione prezzi degli asset (via normalizzazione o non)
            self.StockPrice = self.df.loc[:,self.IndexName]/self.df.loc[0,self.IndexName]
        else:
            self.StockPrice = self.df.loc[:,self.IndexName]

        self.date                = pd.to_datetime(self.df['Date'], format = '%d/%m/%Y')     # Date della serie storica
        self.initial_w           = pd.Series(data = initial_w, index = self.IndexName)      # Setting pesi teorici (valori da mantenere in PTF)
        self.w                   = self.initial_w                                           # Inizializzazione dei pesi effettivi
        self.delta_notional      = 0.0
        self.AssetValue          = self.TotValue*self.w                                     # Inizializzazione valore degli asset in PTF
        self.PMC                 = self.StockPrice.loc[0,:]                                 # Inizializzazione Prezzo Medio di Carico
        self.PMC_weight          = pd.Series(data = 1.0, index = self.IndexName)            # Inizializzazione denominatore media pesata per calcolo PMC
        self.notional            = self.AssetValue/self.StockPrice.loc[0,:]                 # Inizializzazione notional degli asset
        self.PercReturn          = 0.0                                                      # Inizializzazione rendimenti percentuali
        self.CompoundReturn      = 1.0                                                      # Inizializzazione rendimenti composti

    def update_TotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        self.TotValue = self.calculate_TotValue(StockPrice)

    # def update_AssetValue(self, StockPrice):
    #     #StockPrice deve essere una Series col nome degli Stock come indici
    #     self.AssetValue = self.calculate_AssetValue(StockPrice)

    def update_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        self.NetTotValue = self.calculate_NetTotValue(StockPrice)

    def update_AssetValue_weight(self,StockPrice):
        self.AssetValue = self.notional * StockPrice
        self.w = self.AssetValue/self.calculate_TotValue(StockPrice)

    def calculate_TotValue(self,StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        return self.notional.dot(StockPrice)

    def calculate_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        return self.calculate_TotValue(StockPrice) + self.TransactionalCost + self.tax

    # def calculate_AssetValue(self, StockPrice):
    #     return self.notional * StockPrice

    def update_Return(self, StockPrice):
        old_NetTotValue = self.NetTotValue
        current_NetTotValue = self.calculate_NetTotValue(StockPrice)
        self.PercReturn = current_NetTotValue/old_NetTotValue - 1.0
        self.CompoundReturn *= 1.0 + self.PercReturn

    def update_PMC(self,StockPrice):
        mask_buy = self.delta_notional > 0
        self.PMC = self.PMC.copy() #?
        self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                              + (self.delta_notional*StockPrice)[mask_buy] )
        #print("Debug 1")
        #print(f"self.PMC_weight[mask_buy] {self.PMC_weight[mask_buy]}")
        #print(f"self.delta_notional[mask_buy] {self.delta_notional[mask_buy]}")
        self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
        #print("Debug 2")
        self.PMC[mask_buy] /= self.PMC_weight[mask_buy]
        #print("Debug 3")

    def update_tax(self,StockPrice):
        mask_tax = (self.delta_notional < 0) & (StockPrice > self.PMC)
        if np.sum(mask_tax) >0:
            self.tax = (self.delta_notional*StockPrice)[mask_tax].sum()*self.tax_rate
        else:
            self.tax = 0.0

    def update_transactional_cost(self, StockPrice):
        self.TransactionalCost = -(abs(self.delta_notional)*StockPrice).sum()*self.transactional_cost_rate

    def update_notional_tax_transaccost(self, StockPrice):
        self.delta_notional = (self.initial_w - self.w)*self.calculate_TotValue(StockPrice)/StockPrice
        self.update_PMC(StockPrice)
        self.update_tax(StockPrice)
        self.update_transactional_cost(StockPrice)
        self.notional += self.delta_notional

    def reset_tax_transaccost(self):
        self.tax = 0.0
        self.TransactionalCost = 0.0

    def reset_delta_notional(self):
        self.delta_notional = 0.0

    def check_rebalance(self):
        if sum( np.abs(self.w - self.initial_w) > self.rebalance_threshold) > 0:
            return True
        else:
            return False
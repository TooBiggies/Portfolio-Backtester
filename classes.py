"""portfolio_evo: semplice motore di backtest per portafogli ribilanciati.

Contiene la classe `portfolio_evo` che rappresenta l'evoluzione di un
portafoglio costruito su una serie storica di prezzi. La classe gestisce:
- normalizzazione prezzi (opzionale),
- calcolo del notional (numero di unità) per asset,
- controllo e applicazione del ribilanciamento verso pesi target,
- calcolo di costi di transazione e imposte sulle plusvalenze realizzate,
- tracking del prezzo medio di carico (PMC) per il calcolo delle imposte.

Il file non modifica la logica di calcolo originale, aggiunge solo
docstring e spiegazioni sulle formule usate.
"""

import numpy as np
import pandas as pd
import os
import sys
import matplotlib.pyplot as plt

class portfolio_evo: #20260131 vincemauro
    """Rappresenta lo stato e le operazioni di un portafoglio ribilanciato.

    Principali concetti:
    - `initial_w`: pesi target (es. [0.6,0.0,...]) che vogliamo mantenere;
    - `w`: pesi correnti calcolati come AssetValue / TotValue;
    - `notional`: numero di unità per ogni asset (AssetValue / prezzo);
    - `delta_notional`: variazione di unità necessaria per ribilanciare ai pesi target;
    - `PMC`: prezzo medio di carico per asset (usato per calcolare le plusvalenze tassabili);

    Formula chiave per il ribilanciamento (unità da comprare/vendere):
        delta_notional = (initial_w - w) * TotValue / StockPrice

    Dove `TotValue` è il valore corrente del portafoglio e `StockPrice` è il
    prezzo corrente per asset. Questa formula deriva dal voler ottenere, dopo
    l'operazione, AssetValue = initial_w * TotValue, e quindi notional = AssetValue / price.
    """

    #20260131 vincemauro reimpostati tutti i valori numerici con virgola per forzare il type a float. Diversamente sono int e alla prima assegnazione con virgola si va in errore.
    colonne_escluse = ["Date"]  # colonne da escludere nell'import del DF nell'oggetto

    def __init__(self, initial_balance, transac_cost_rate, tax_rate, exp_rate, rebalance_threshold,
                 initial_w, imported_dataframe, start_date=None, end_date=None, stock_price_normalization = True):
        """Inizializza lo stato del portafoglio.

        Parametri principali:
        - initial_balance: capitale iniziale (valore monetario)
        - transac_cost_rate: % di costo applicata alle operazioni (commissioni+spread)
        - tax_rate: aliquota fiscale sulle plusvalenze realizzate
        - exp_rate: spese correnti (tracking + bollo) - non usato direttamente nei calcoli qui
        - rebalance_threshold: soglia su deviazione di peso che attiva il ribilanciamento
        - initial_w: pesi target (list o array) con lunghezza pari al numero di asset
        - imported_dataframe: DataFrame contenente colonna 'Date' e colonne prezzi per asset
        - stock_price_normalization: se True normalizza i prezzi dividendo per il primo valore
        """

        self.StartValue               = initial_balance         # Valore iniziale del PTF - vincemauro 20260131
        self.TotValue                 = initial_balance         # Valore totale del PTF
        self.NetTotValue              = self.TotValue           # Valore totale del PTF sottraendo  tasse e costi di transazione
        self.transactional_cost_rate  = transac_cost_rate       # Percentuale costi di transazione come somma %commissioni e %spread
        self.TransactionalCost        = 0.0                     # Inizializzazione costo di transazione progressivo
        self.tax_rate                 = tax_rate                # Percentuale tassazione plusvalenza
        self.exp_rate                 = exp_rate                # Tasso spesa annuo in cui inserire la somma di tracking error + 0.2% di imposta di bollo sul dossier titoli
        self.tax                      = 0.0                     # Inizializzazione tassazione progressiva
        self.rebalance_threshold      = rebalance_threshold     # Soglia per effettuare il ribilanciamento dei pesi
        self.df                       = imported_dataframe
        
        if start_date is not None:
            self.start_date = pd.to_datetime(start_date)
            self.df  = self.df[(self.df["Date"]>=self.start_date)].copy()
        
        if end_date is not None:
            self.end_date = pd.to_datetime(end_date)
            self.df  = self.df[(self.df["Date"]<=self.end_date)].copy()
            
        self.df = self.df.reset_index(drop=True)

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
        self.immediate_payments  = 0.0                                                      # cash adjustments (taxes/fees paid immediately)
        self.GrossValue = float(self.TotValue)                                              # market value without costs/taxes
        self.BrokerValue = float(self.TotValue)                                             # market value as seen at broker (includes paid fees)
        self.NetValue = float(self.TotValue)                                                # liquidation value (after taxes and liquidation costs)

    def update_TotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        # Update Gross/Broker/Net values and keep TotValue as broker view for compatibility
        gross = self.calculate_TotValue(StockPrice)
        self.GrossValue = gross
        self.BrokerValue = gross + self.immediate_payments
        # TotValue preserved as broker view (market value plus any cash adjustments)
        self.TotValue = float(self.BrokerValue)
        # compute NetValue = value if liquidated now (subtract liquidation TC and taxes on realized gains)
        try:
            liq_tc = (abs(self.notional) * StockPrice).sum() * self.transactional_cost_rate
        except Exception:
            liq_tc = 0.0
        # tax on full liquidation: sum over assets of max((price - PMC) * notional, 0) * tax_rate
        try:
            gains = (StockPrice - self.PMC) * self.notional
            taxable = gains[gains > 0].sum()
            tax_liab = float(taxable) * float(self.tax_rate)
        except Exception:
            tax_liab = 0.0
        self.NetValue = float(gross) + float(self.immediate_payments) - float(liq_tc) - float(tax_liab)

    # def update_AssetValue(self, StockPrice):
    #     #StockPrice deve essere una Series col nome degli Stock come indici
    #     self.AssetValue = self.calculate_AssetValue(StockPrice)

    def update_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        self.NetTotValue = self.calculate_NetTotValue(StockPrice)

    def update_AssetValue_weight(self,StockPrice):
        """Aggiorna `AssetValue` e i pesi correnti `w` dati i prezzi attuali.

        AssetValue = notional * price
        w = AssetValue / TotValue
        """
        self.AssetValue = self.notional * StockPrice
        self.w = self.AssetValue/self.calculate_TotValue(StockPrice)

    def calculate_TotValue(self,StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        """Valore totale del portafoglio come dot product tra notional e prezzi."""
        return self.notional.dot(StockPrice)

    def calculate_NetTotValue(self, StockPrice):
        #StockPrice deve essere una Series col nome degli Stock come indici
        """Valore netto che include costi transazionali e imposte (valori negativi)."""
        return self.calculate_TotValue(StockPrice) + self.TransactionalCost + self.tax

    # def calculate_AssetValue(self, StockPrice):
    #     return self.notional * StockPrice

    def update_Return(self, StockPrice):
        """Calcola il rendimento percentuale del periodo e aggiorna il rendimento composto.

        Usa `NetTotValue` (che include costi e tasse) per ottenere rendimenti netti.
        """
        old_NetTotValue = self.NetTotValue
        current_NetTotValue = self.calculate_NetTotValue(StockPrice)
        self.PercReturn = current_NetTotValue/old_NetTotValue - 1.0
        self.CompoundReturn *= 1.0 + self.PercReturn

    def update_PMC(self,StockPrice):
        """Aggiorna il Prezzo Medio di Carico (`PMC`) quando si acquistano unità.

        Per gli asset per cui `delta_notional > 0` (acquisto), il nuovo PMC è la
        media pesata tra il vecchio PMC e il valore delle nuove unità acquistate
        (delta_notional * price). `PMC_weight` è il denominatore cumulato usato
        per calcolare la media pesata.
        """
        mask_buy = self.delta_notional > 0
        self.PMC = self.PMC.copy()
        self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                              + (self.delta_notional*StockPrice)[mask_buy] )
        self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
        self.PMC[mask_buy] /= self.PMC_weight[mask_buy]

    def update_tax(self,StockPrice):
        """Calcola le imposte sulle plusvalenze realizzate.
        Si applica la tassa solo se si vendono quote (`delta_notional < 0`) e il
        prezzo di realizzo è maggiore del `PMC` (plusvalenza). L'importo tassato
        è la somma delle plusvalenze realizzate per asset, cioè
        sum( - delta_notional * (price - PMC) for vendite con price > PMC ) * tax_rate.
        Nota: `delta_notional` è negativo per vendite; l'espressione calcola
        la plusvalenza positiva prima di moltiplicare per `tax_rate`.
        """
        mask_tax = (self.delta_notional < 0) & (StockPrice > self.PMC)
        if np.sum(mask_tax) > 0:
            # realized gains: for sells (delta_notional < 0) compute -(delta * (price - PMC))
            realized_gains = - (self.delta_notional * (StockPrice - self.PMC))[mask_tax].sum()
            self.tax = float(realized_gains) * float(self.tax_rate)
        else:
            self.tax = 0.0

    def update_transactional_cost(self, StockPrice):
        """Calcola il costo transazionale come percentuale del controvalore scambiato.

        Viene usata la somma del valore assoluto delle variazioni di notional
        (|delta_notional| * prezzo) e moltiplicata per il tasso di costo.
        Il risultato è negativo (costo) e viene sommato a NetTotValue.
        """
        self.TransactionalCost = -(abs(self.delta_notional)*StockPrice).sum()*self.transactional_cost_rate

    def update_notional_tax_transaccost(self, StockPrice):
        """Calcola e applica la variazione di notional per ribilanciare ai pesi target.

        Steps:
        1. delta_notional = (initial_w - w) * TotValue / price  (unità da comprare/vendere)
        2. aggiorna PMC per le eventuali compravendite
        3. calcola imposte e costi transazionali
        4. aggiorna il `notional` (numero di unità) con `notional += delta_notional`

        Nota: l'ordine è importante perché PMC deve riflettere gli acquisti prima di
        calcolare eventuali imposte su vendite; qui si usa l'ordine implementato
        originariamente dall'autore.
        """
        self.delta_notional = (self.initial_w - self.w)*self.calculate_TotValue(StockPrice)/StockPrice
        self.update_PMC(StockPrice)
        # compute taxes and transaction costs (these are amounts, tax/TransactionalCost
        # are negative when they represent payments)
        self.update_tax(StockPrice)
        self.update_transactional_cost(StockPrice)
        # update notional quantities
        self.notional += self.delta_notional
        # record immediate payments (taxes + transaction costs) as cash adjustment
        try:
            self.immediate_payments += (self.tax + self.TransactionalCost)
        except Exception:
            pass

    def reset_tax_transaccost(self):
        self.tax = 0.0
        self.TransactionalCost = 0.0

    def reset_delta_notional(self):
        self.delta_notional = 0.0

    def check_rebalance(self):
        """Controlla se qualche asset supera la soglia di deviazione e richiede ribilanciamento.

        Restituisce True se esiste almeno un asset per cui |w - initial_w| > rebalance_threshold.
        """
        if sum( np.abs(self.w - self.initial_w) > self.rebalance_threshold) > 0:
            return True
        else:
            return False
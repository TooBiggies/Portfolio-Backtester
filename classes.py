"""portfolio_evo: semplice motore di backtest per portafogli ribilanciati.

Contiene la classe `portfolio_evo` che rappresenta l'evoluzione di un
portafoglio costruito su una serie storica di prezzi. La classe gestisce:
- normalizzazione prezzi (opzionale),
- calcolo del notional (numero di unità) per asset,
- controllo e applicazione del ribilanciamento verso pesi target,
- calcolo di costi di transazione e imposte sulle plusvalenze realizzate,
- tracking del prezzo medio di carico (PMC) per il calcolo delle imposte,
- riporto delle minusvalenze realizzate fino a 4 anni (art. 68 TUIR),
- applicazione pro-rata giornaliera delle spese ricorrenti (exp_rate).
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
                 initial_w, imported_dataframe, start_date=None, end_date=None, stock_price_normalization = True,
                 calcola_minusvalenze: bool = False):
        """Inizializza lo stato del portafoglio.

        Parametri principali:
        - initial_balance: capitale iniziale (valore monetario)
        - transac_cost_rate: % di costo applicata alle operazioni (commissioni+spread)
        - tax_rate: aliquota fiscale sulle plusvalenze realizzate
        - exp_rate: spese correnti annue (tracking difference + imposta di bollo); applicate
          pro-rata su base giorni di calendario tramite `update_exp_cost()`
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
        self.exp_cost                 = 0.0                     # Costo ricorrente pro-rata dell'ultimo periodo
        self.loss_carryforward        = {}                      # Riporto minusvalenze: {anno: importo} (art. 68 TUIR, max 4 anni)
        self.calcola_minusvalenze     = calcola_minusvalenze    # Se False (default) il riporto è disabilitato
        self._prev_date               = None                    # Data dell'ultimo aggiornamento spese ricorrenti
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
        self.notional            = self.AssetValue/self.StockPrice.loc[0,:]                 # Inizializzazione notional degli asset
        self.PMC_weight          = self.notional.copy()                                      # Denominatore media pesata PMC = unità detenute inizialmente
        self.PercReturn          = 0.0                                                      # Inizializzazione rendimenti percentuali
        self.CompoundReturn      = 1.0                                                      # Inizializzazione rendimenti composti
        self.immediate_payments  = 0.0                                                      # cash adjustments (taxes/fees paid immediately)
        self.GrossValue = float(self.TotValue)                                              # market value without costs/taxes
        self.BrokerValue = float(self.TotValue)                                             # market value as seen at broker (includes paid fees)
        self.NetValue = float(self.TotValue)                                                # liquidation value (after taxes and liquidation costs)
        self.initial_transactional_cost = 0.0                                               # costo transazionale dell'acquisto iniziale (day 0)

        # Apply transaction costs for the initial buy on day 0, as an immediate payment.
        try:
            if self.transactional_cost_rate and self.transactional_cost_rate != 0:
                initial_tc = -(abs(self.notional) * self.StockPrice.loc[0, :]).sum() * self.transactional_cost_rate
                self.initial_transactional_cost = float(initial_tc)
                self.immediate_payments += self.initial_transactional_cost
        except Exception:
            pass

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
        # tax on full liquidation: gains net of available carry-forward losses
        try:
            gains = (StockPrice - self.PMC) * self.notional
            taxable = float(gains[gains > 0].sum())
            available_offset = sum(self.loss_carryforward.values())
            net_taxable = max(0.0, taxable - available_offset)
            tax_liab = net_taxable * float(self.tax_rate)
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
        """Aggiorna il Prezzo Medio di Carico (`PMC`) in base agli acquisti e alle vendite.

        Per gli acquisti (`delta_notional > 0`): il PMC viene aggiornato come media
        pesata tra il vecchio PMC e il prezzo delle nuove unità acquistate.
        Per le vendite (`delta_notional < 0`): il PMC non cambia, ma `PMC_weight`
        (il denominatore = unità detenute) viene ridotto per mantenere la coerenza
        con i successivi aggiornamenti.
        """
        mask_buy  = self.delta_notional > 0
        mask_sell = self.delta_notional < 0
        self.PMC = self.PMC.copy()
        # Acquisti: aggiorna PMC come media pesata
        self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                              + (self.delta_notional*StockPrice)[mask_buy] )
        self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
        self.PMC[mask_buy] /= self.PMC_weight[mask_buy]
        # Vendite: PMC invariato, riduce solo il denominatore (delta < 0)
        self.PMC_weight[mask_sell] += self.delta_notional[mask_sell]

    def update_tax(self, StockPrice, current_date=None):
        """Calcola le imposte sulle plusvalenze realizzate, con riporto minusvalenze.

        Per ogni vendita (`delta_notional < 0`) calcola il risultato per asset:
          per-asset = -(delta * (price - PMC))  # positivo = plusvalenza, negativo = minusvalenza

        Le plusvalenze e minusvalenze della stessa operazione si compensano prima
        (netting intra-operazione). Se `current_date` è fornita, attiva il regime
        dello "zainetto fiscale" (art. 68 TUIR): le minusvalenze nette vengono
        accumulate per anno e usate per compensare le plusvalenze future, a scalare
        dai crediti più vecchi, con scadenza a 4 anni dal realizzo.
        Se `current_date` è None, si usa un percorso semplificato senza riporto
        (compatibilità backward con test diretti).
        """
        mask_sell = self.delta_notional < 0
        if int(np.sum(mask_sell)) == 0:
            self.tax = 0.0
            return

        # Per ogni vendita: positivo = plusvalenza, negativo = minusvalenza
        by_asset = -(self.delta_notional * (StockPrice - self.PMC))[mask_sell]
        realized_gains = float(by_asset[by_asset > 0].sum())
        realized_losses = float((-by_asset[by_asset < 0]).sum())  # importo positivo

        if current_date is None:
            # percorso senza riporto (compatibilità backward)
            self.tax = -float(realized_gains) * float(self.tax_rate)
            return

        if not self.calcola_minusvalenze:
            # riporto minusvalenze disabilitato: tassa solo le plusvalenze nette dell'operazione
            net = realized_gains - realized_losses
            self.tax = -float(max(0.0, net)) * float(self.tax_rate)
            return

        current_year = pd.Timestamp(current_date).year
        # scadenza crediti più vecchi di 4 anni (art. 68 TUIR)
        self.loss_carryforward = {
            y: v for y, v in self.loss_carryforward.items()
            if current_year - y <= 4
        }

        # netting intra-operazione: le perdite dello stesso evento compensano i guadagni
        same_tx_net = realized_gains - realized_losses
        if same_tx_net >= 0:
            net_gains_after_netting = same_tx_net
            new_carry_losses = 0.0
        else:
            net_gains_after_netting = 0.0
            new_carry_losses = -same_tx_net

        # compensazione con il riporto disponibile (dal credito più vecchio)
        available = sum(self.loss_carryforward.values())
        usable = min(available, net_gains_after_netting)
        net_taxable = net_gains_after_netting - usable
        remaining = usable
        for y in sorted(self.loss_carryforward.keys()):
            if remaining <= 1e-10:
                break
            used = min(self.loss_carryforward[y], remaining)
            self.loss_carryforward[y] -= used
            remaining -= used
        self.loss_carryforward = {y: v for y, v in self.loss_carryforward.items() if v > 1e-10}

        # accumula nuove minusvalenze nette nel bucket dell'anno corrente
        if new_carry_losses > 0:
            self.loss_carryforward[current_year] = (
                self.loss_carryforward.get(current_year, 0.0) + new_carry_losses
            )
        self.tax = -float(net_taxable) * float(self.tax_rate)

    def update_transactional_cost(self, StockPrice):
        """Calcola il costo transazionale come percentuale del controvalore scambiato.

        Viene usata la somma del valore assoluto delle variazioni di notional
        (|delta_notional| * prezzo) e moltiplicata per il tasso di costo.
        Il risultato è negativo (costo) e viene sommato a NetTotValue.
        """
        self.TransactionalCost = -(abs(self.delta_notional)*StockPrice).sum()*self.transactional_cost_rate

    def update_notional_tax_transaccost(self, StockPrice, current_date=None):
        """Calcola e applica la variazione di notional per ribilanciare ai pesi target.

        Steps:
        1. delta_notional = (initial_w - w) * TotValue / price  (unità da comprare/vendere)
        2. aggiorna PMC per le eventuali compravendite
        3. calcola imposte e costi transazionali
        4. aggiorna il `notional` (numero di unità) con `notional += delta_notional`

        `current_date` è passata a `update_tax` per attivare il riporto minusvalenze.
        Nota: l'ordine è importante perché PMC deve riflettere gli acquisti prima di
        calcolare eventuali imposte su vendite; qui si usa l'ordine implementato
        originariamente dall'autore.
        """
        self.delta_notional = (self.initial_w - self.w)*self.calculate_TotValue(StockPrice)/StockPrice
        self.update_PMC(StockPrice)
        # compute taxes and transaction costs (these are amounts, tax/TransactionalCost
        # are negative when they represent payments)
        self.update_tax(StockPrice, current_date=current_date)
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
        self.exp_cost = 0.0

    def reset_delta_notional(self):
        self.delta_notional = 0.0

    def update_exp_cost(self, current_date, StockPrice):
        """Applica le spese ricorrenti annuali (imposta di bollo + tracking difference) pro-rata.

        Il costo è proporzionale al valore di mercato del portafoglio e ai giorni di
        calendario trascorsi dall'ultima chiamata (giorni / 365.25). Viene sottratto
        come pagamento immediato (valore negativo in `immediate_payments`).
        Al primo invoco inizializza la data di riferimento senza addebitare costi.
        """
        current_date = pd.Timestamp(current_date)
        if self._prev_date is None:
            self._prev_date = current_date
            self.exp_cost = 0.0
            return
        days = (current_date - self._prev_date).days
        if days <= 0:
            self.exp_cost = 0.0
            return
        gross = self.calculate_TotValue(StockPrice)
        self.exp_cost = -float(gross) * float(self.exp_rate) * (days / 365.25)
        self.immediate_payments += self.exp_cost
        self._prev_date = current_date

    def check_rebalance(self):
        """Controlla se qualche asset supera la soglia di deviazione e richiede ribilanciamento.

        Restituisce True se esiste almeno un asset per cui |w - initial_w| > rebalance_threshold.
        """
        if sum( np.abs(self.w - self.initial_w) > self.rebalance_threshold) > 0:
            return True
        else:
            return False

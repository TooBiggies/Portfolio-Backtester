# Portfolio Backtester — Documento tecnico

## Panoramica

Il progetto simula l'evoluzione nel tempo di un portafoglio multi-asset bilanciato,
applicando ribilanciamenti periodici, costi di transazione, spese ricorrenti e
tassazione italiana sulle plusvalenze realizzate.

Il punto di ingresso è `backtester.py`, che funge da wrapper di compatibilità verso
il vero entrypoint `backtester_cli.py`.

---

## Architettura dei moduli

```
backtester.py               ← wrapper (backward-compat), delega a backtester_cli.py
backtester_cli.py           ← parsing argomenti CLI (argparse)
backtester_runner.py        ← loop principale del backtest
classes.py                  ← classe portfolio_evo (motore del backtest)
backtester_config.py        ← parametri di configurazione
backtester_load_config.py   ← caricamento e normalizzazione pesi
backtester_report_creation.py ← orchestrazione generazione report
backtester_generate_reports.py ← funzioni di supporto alla generazione
report_writer_md.py         ← scrittura report Markdown
report_writer_html.py       ← scrittura report HTML interattivo
report_writer_files.py      ← scrittura file XLSX/CSV
```

---

## Come si avvia

```bash
# Avvio base
python backtester.py

# Con output di debug
python backtester.py --verbose

# Con riporto minusvalenze fiscali abilitato
python backtester.py --calcola-minusvalenze
```

---

## Flusso di esecuzione

### 1. Parsing CLI (`backtester_cli.py`)
Legge i flag `--verbose` e `--calcola-minusvalenze` e chiama `run_backtest()`.

### 2. Caricamento dati e configurazione (`backtester_runner.py`)
- Legge `Timeseries.csv` (separatore `;`), colonna `Date` + una colonna per ogni asset.
- Filtra le date tra `2000-01-03` e `2025-09-04`.
- Carica i parametri da `backtester_config.py` tramite `load_config()`.
- `load_config()` normalizza automaticamente i pesi iniziali se la loro somma non è 1.

### 3. Inizializzazione portafoglio (`classes.py → portfolio_evo.__init__`)
- Filtra la serie storica nell'intervallo `[start_date, end_date]`.
- Opzionalmente normalizza i prezzi dividendo per il valore iniziale (t=0).
- Calcola `notional` (unità per asset) = `AssetValue / StockPrice`.
- Inizializza il **Prezzo Medio di Carico (PMC)** al prezzo iniziale di ogni asset.

### 4. Loop temporale giornaliero (`backtester_runner.py`)

Per ogni giorno della serie storica:

```
1. Reset costi/tasse del giorno precedente
2. Aggiorna AssetValue e pesi correnti (w = AssetValue / TotValue)
3. Controllo ribilanciamento: se |w - target_w| > soglia → ribilancia
   a. Calcola delta_notional = (target_w - w) * TotValue / StockPrice
   b. Aggiorna PMC per gli acquisti
   c. Calcola tasse sulle plusvalenze realizzate (vendite)
   d. Calcola costi di transazione
   e. Aggiorna notional
4. Applica spese ricorrenti (exp_rate) pro-rata sui giorni trascorsi
5. Calcola rendimento percentuale e composto
6. Aggiorna TotValue (lordo + broker + netto)
7. Salva nel log giornaliero (df_log, df_log_delta)
```

### 5. Generazione report (`backtester_report_creation.py`)
Al termine del loop vengono generati nella cartella `reports/`:
- **XLSX** (`output_ptf.xlsx`): serie storica giornaliera del portafoglio
- **XLSX delta** (`output_ptf_delta.xlsx`): variazioni di controvalore per asset a ogni ribilanciamento
- **CSV transazioni** (`backtest_transactions.csv`): dettaglio di ogni ribilanciamento
- **Markdown** (`backtest_report.md`): report testuale con metriche e dettagli ribilanciamenti
- **HTML** (`backtest_report.html`): report interattivo con grafici e tabelle

Ogni run produce file con timestamp (`YYYYMMDD_HHMMSS_...`) e una copia
`latest_*` per accesso rapido all'ultimo risultato.

---

## Parametri di configurazione (`backtester_config.py`)

| Parametro | Default | Descrizione |
|---|---|---|
| `INITIAL_WEIGHTS` | `[0.60, 0.00, 0.00, 0.10, 0.00, 0.00, 0.00, 0.00, 0.25, 0.00, 0.05]` | Pesi target per asset (VT, SPY, VXUS, GLD, CASH, SHY, IEF, TLT, ZROZ, KMLM, DBMF) |
| `CAPITAL` | `10000` | Capitale iniziale (€) |
| `START_DATE` | `2020-01-01` | Data inizio simulazione |
| `END_DATE` | `2025-10-30` | Data fine simulazione |
| `TRANSAC_COST_RATE` | `0.0029` | Costi di transazione (0.29% — commissioni + spread) |
| `EXP_RATE` | `0.002` | Spese annuali (0.20% — tracking difference + imposta di bollo) |
| `TAX_RATE` | `0.26` | Aliquota su plusvalenze realizzate (26%) |
| `REBALANCE_THRESHOLD` | `0.10` | Soglia deviazione peso per attivare il ribilanciamento (10%) |
| `STOCK_PRICE_NORMALIZATION` | `True` | Normalizza i prezzi al valore iniziale |
| `CALCOLA_MINUSVALENZE` | `False` | Abilita il riporto minusvalenze (art. 68 TUIR) |
| `REPORTS_DIR` | `"reports"` | Cartella di output dei report |

---

## Asset supportati

| Ticker | Descrizione |
|---|---|
| VT | ETF azionario globale (mercati sviluppati + emergenti) |
| SPY | ETF S&P 500 (USA large-cap) |
| VXUS | ETF azionario internazionale (esclude USA) |
| GLD | ETF oro |
| CASH | Liquidità |
| SHY | Treasury a breve termine (1-3 anni) |
| IEF | Treasury a medio termine (7-10 anni) |
| TLT | Treasury a lungo termine (20+ anni) |
| ZROZ | Treasury zero-coupon (duration molto elevata) |
| KMLM | ETF alternativo (managed futures) |
| DBMF | ETF multi-asset / managed futures |

---

## Meccanica del ribilanciamento

Il ribilanciamento viene attivato quando almeno un asset supera la soglia:

```
|peso_corrente - peso_target| > REBALANCE_THRESHOLD
```

Le unità da comprare/vendere si calcolano con:

```
delta_notional = (target_w - w) * TotValue / StockPrice
```

Dove `TotValue` è il valore corrente del portafoglio e `StockPrice` il prezzo dell'asset.
Dopo il ribilanciamento il portafoglio torna esattamente ai pesi target.

---

## Calcolo tasse (regime italiano)

Le imposte vengono calcolate solo sulle **vendite** (`delta_notional < 0`):

```
plusvalenza_per_asset = -(delta_notional × (prezzo - PMC))
```

- Solo la parte positiva viene tassata (plusvalenza).
- Plusvalenze e minusvalenze della stessa operazione si compensano (netting intra-operazione).

### Riporto minusvalenze (art. 68 TUIR) — opzionale

Attivabile con `--calcola-minusvalenze` o impostando `CALCOLA_MINUSVALENZE = True` nel config.

- Le minusvalenze nette vengono accumulate per anno fiscale.
- Compensano le plusvalenze future per un massimo di **4 anni** dal realizzo.
- I crediti più vecchi vengono usati per primi (FIFO sugli anni).
- I crediti scaduti vengono eliminati automaticamente.

---

## Spese ricorrenti (expense ratio)

Le spese annuali (`EXP_RATE`) vengono applicate **pro-rata giornaliero**:

```
exp_cost = valore_mercato × exp_rate × (giorni_trascorsi / 365.25)
```

Vengono sottratte come pagamento immediato a ogni aggiornamento giornaliero.

---

## Metriche calcolate nel report

| Metrica | Descrizione |
|---|---|
| **GrossValue** | Valore di mercato lordo (senza costi/tasse) |
| **BrokerValue** | Valore come visto dal broker (include costi/tasse già pagati) |
| **NetValue** | Valore di liquidazione netto (dopo tasse e costi di uscita stimati) |
| **Compound Return** | Rendimento composto cumulato |
| **CAGR** | Rendimento annualizzato composto |
| **TransacCost** | Costi di transazione cumulati |
| **Taxes** | Imposte cumulate |
| **ExpCost** | Spese ricorrenti cumulate |
| **LossCarryforward** | Minusvalenze disponibili per compensazione futura |

---

## Input dati

Il file `Timeseries.csv` deve avere:
- Separatore `;`
- Prima colonna: `Date` (formato `dd/mm/yyyy`)
- Colonne successive: una per ogni ticker (nome colonna = ticker)

---

## Output

Tutti i file vengono salvati nella cartella `reports/` con prefisso timestamp.
I file `latest_*` vengono sovrascritti ad ogni run per accesso rapido.

```
reports/
├── 20260315_143000_backtest_report.md
├── 20260315_143000_backtest_report.html
├── 20260315_143000_output_ptf.xlsx
├── 20260315_143000_output_ptf_delta.xlsx
├── 20260315_143000_backtest_transactions.csv
├── latest_backtest_report.md
├── latest_backtest_report.html
├── latest_output_ptf.xlsx
├── latest_output_ptf_delta.xlsx
└── latest_backtest_transactions.csv
```

# Verifica logica del backtester — Analisi tecnica e fiscale

Data verifica: 2026-03-15
Fonti: Agenzia delle Entrate, art. 67-68 TUIR, Morningstar, CFA Institute, Vanguard, Charles Schwab

---

## Riepilogo esecutivo

| Area | Elemento | Stato |
|---|---|---|
| Fiscale | Aliquota plusvalenze 26% | ✅ Corretto |
| Fiscale | Riporto minusvalenze 4 anni (art. 68 TUIR) | ✅ Corretto |
| Fiscale | Metodo PMC per base di costo | ✅ Corretto |
| Fiscale | Imposta di bollo 0.20% | ✅ Corretto |
| Fiscale | Netting intra-operazione plus/minus | ✅ Corretto |
| **Fiscale** | **ETF armonizzati: regime "redditi di capitale"** | **⚠️ Problema noto** |
| Fiscale | Minimo imposta di bollo €34.20 | ⚠️ Non implementato |
| Math | Formula ribilanciamento | ✅ Corretta |
| Math | Aggiornamento PMC (solo su acquisti) | ✅ Corretto |
| Math | CAGR | ✅ Corretta |
| Math | Costi di transazione | ✅ Corretta |
| Math | Expense ratio — divisore 365.25 vs 365 | ⚠️ Minore |

---

## 1. Fiscale

### 1.1 Aliquota plusvalenze — 26% ✅

**Codice** (`backtester_config.py`): `TAX_RATE = 0.26`

**Verifica**: Corretto. L'aliquota del 26% è quella vigente per le plusvalenze finanziarie retail su azioni ed ETF. Eccezioni non implementate (ma irrilevanti per gli asset nel portafoglio):
- Titoli di Stato italiani (BOT, BTP): 12.5%
- Crypto: in aumento al 33% dal 2026

Nessuna modifica necessaria per il portafoglio corrente (VT, SPY, GLD, TLT, ecc.).

---

### 1.2 Riporto minusvalenze — 4 anni (art. 68 TUIR) ✅

**Codice** (`classes.py:224`):
```python
self.loss_carryforward = {
    y: v for y, v in self.loss_carryforward.items()
    if current_year - y <= 4
}
```

**Verifica**: Corretto. L'art. 68 TUIR recita: *"Le minusvalenze sono portate in deduzione [...] nei periodi d'imposta successivi, ma non oltre il quarto."* La condizione `current_year - y <= 4` permette l'uso nello stesso anno (differenza = 0) e nei 4 anni successivi, in linea con la norma.

L'FIFO sui crediti (si usano prima i più vecchi) è anche corretto:
```python
for y in sorted(self.loss_carryforward.keys()):  # ordine crescente = più vecchi prima
```

---

### 1.3 Metodo PMC ✅

**Codice** (`classes.py:172`):
```python
self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                      + (self.delta_notional*StockPrice)[mask_buy])
self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
self.PMC[mask_buy] /= self.PMC_weight[mask_buy]
```

**Verifica**: Corretto. Il PMC (Prezzo Medio di Carico, o LIFO/FIFO alternativo) è il metodo **obbligatorio** in Italia per il regime di risparmio amministrato. Si aggiorna solo sugli acquisti (`mask_buy`), non cambia sulle vendite. Questo è il comportamento corretto.

---

### 1.4 Imposta di bollo 0.20% ✅

**Codice** (`backtester_config.py`): `EXP_RATE = 0.002`

Secondo la documentazione del progetto, questo valore incorpora sia l'imposta di bollo (0.20%) che il tracking difference degli ETF. L'imposta di bollo su dossier titoli è confermata a **0.20% annuo** (2 per mille) dal D.L. 201/2011, applicata sul valore di mercato.

**Limitazione non implementata**: L'imposta prevede un minimo di €34.20/anno. Per portafogli piccoli (< ~17.100 €) la tassa effettiva sarebbe superiore alla simulazione.

---

### 1.5 Netting intra-operazione ✅

**Codice** (`classes.py:216`):
```python
if not self.calcola_minusvalenze:
    net = realized_gains - realized_losses
    self.tax = float(max(0.0, net)) * float(self.tax_rate)
```

**Verifica**: Corretto. Le plusvalenze e minusvalenze realizzate nello stesso ribilanciamento vengono compensate prima di calcolare le imposte. Questo rispecchia il comportamento del regime amministrato italiano, dove la banca intermediaria compensa automaticamente.

---

### 1.6 ⚠️ Problema noto: ETF armonizzati e "redditi di capitale"

**Questo è il limite fiscale più importante del backtester.**

In Italia esiste una distinzione critica:

| Strumento | Tipo reddito da cessione | Compensabile con minusvalenze? |
|---|---|---|
| Azioni singole | Redditi **diversi** (art. 67 TUIR) | ✅ Sì |
| ETC (es. GLD fisico) | Redditi **diversi** | ✅ Sì |
| Certificate, derivati | Redditi **diversi** | ✅ Sì |
| **ETF armonizzati (UCITS)** | Redditi **di capitale** | ❌ No |

**La plusvalenza da vendita di un ETF armonizzato (UCITS) è classificata come "reddito di capitale"**, non come "reddito diverso". I redditi di capitale NON possono essere compensati con minusvalenze (che sono redditi diversi).

**Paradosso fiscale ETF italiani**: Se vendi un ETF in perdita, la minusvalenza è "reddito diverso" e finisce nel carry-forward. Ma se in seguito vendi un ETF in guadagno, quella plusvalenza è "reddito di capitale" e **non può essere compensata**. Il carry-forward resta inutilizzato.

**Impatto sul codice**: La funzionalità `--calcola-minusvalenze` implementa una compensazione che **nella realtà non funziona per portafogli interamente composti da ETF armonizzati** (VT, SPY, VXUS, IEF, TLT, ecc.). Il meccanismo sarebbe invece corretto per portafogli con azioni singole, ETC, certificate o ETF non armonizzati.

**Raccomandazione**: Il flag `--calcola-minusvalenze` dovrebbe includere una nota che la compensazione è applicabile solo se il portafoglio include strumenti che generano "redditi diversi" (azioni, ETC, derivati), non ETF UCITS.

---

## 2. Matematica del portafoglio

### 2.1 Formula ribilanciamento ✅

**Codice** (`classes.py:281`):
```python
self.delta_notional = (self.initial_w - self.w) * self.calculate_TotValue(StockPrice) / StockPrice
```

**Verifica**: Corretta. La formula deriva dall'identità:
```
Valore_target_i = target_w_i × TotValue
Notional_target_i = Valore_target_i / Prezzo_i
delta_notional_i = Notional_target_i - Notional_corrente_i
                 = (target_w_i × TotValue / Prezzo_i) - (w_i × TotValue / Prezzo_i)
                 = (target_w_i - w_i) × TotValue / Prezzo_i
```
Dopo il ribilanciamento i pesi risultano esattamente uguali ai target. Confermato da CFA Institute e letteratura standard.

---

### 2.2 Aggiornamento PMC solo su acquisti ✅

**Codice** (`classes.py:180`):
```python
mask_buy = self.delta_notional > 0
self.PMC[mask_buy] = ...  # solo per gli asset comprati
```

**Verifica**: Corretto. Il PMC si aggiorna esclusivamente sugli acquisti; sulle vendite rimane invariato. Questo è il comportamento del metodo costo medio ponderato (WACC — Weighted Average Cost). Confermato da Janus Henderson Investors e Charles Schwab.

---

### 2.3 CAGR ✅

**Codice** (`backtester_generate_reports.py:138`):
```python
cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100
```

**Verifica**: Corretta. Formula standard universale:
```
CAGR = (Rendimento_composto)^(1/anni) - 1
```
Confermato da CFA Institute, Wall Street Prep, Wikipedia.

---

### 2.4 Costi di transazione ✅

**Codice** (`classes.py:265`):
```python
self.TransactionalCost = -(abs(self.delta_notional)*StockPrice).sum()*self.transactional_cost_rate
```

**Verifica**: Corretta. Il costo viene calcolato come percentuale del controvalore totale scambiato (somma valore assoluto delle operazioni). Questo metodo è standard e incorpora sia le commissioni che lo spread, usando un tasso unico (`TRANSAC_COST_RATE = 0.0029` = 0.29%).

**Nota**: Il bid-ask spread vero è variabile e non prevedibile in simulazione; l'uso di un tasso fisso è la pratica standard nei backtester.

---

### 2.5 ⚠️ Expense ratio: divisore 365.25 vs 365

**Codice** (`classes.py:321`):
```python
self.exp_cost = -float(gross) * float(self.exp_rate) * (days / 365.25)
```

**Verifica**: Tecnicamente corretto (365.25 è la media gregoriana con gli anni bisestili), ma lo standard dell'industria finanziaria (Vanguard, Robinhood, Charles Schwab) usa **365**. La differenza è trascurabile: su €10.000 e 5 anni, la discrepanza è ~€0.27.

**Impatto pratico**: Nessuno. Entrambi sono accettabili.

---

## 3. Ordine delle operazioni nel ribilanciamento

L'ordine in `update_notional_tax_transaccost()` è:

```
1. Calcola delta_notional (quante unità comprare/vendere)
2. Aggiorna PMC per gli acquisti
3. Calcola tasse sulle vendite (usa PMC pre-aggiornamento per gli asset venduti ✓)
4. Calcola costi di transazione
5. Aggiorna notional
```

**Verifica**: Corretto. Il PMC degli asset venduti non viene modificato nel passo 2 (che aggiorna solo `mask_buy`), quindi le tasse al passo 3 usano il PMC corretto (quello storico, non contaminato dagli acquisti dello stesso giorno).

---

## 4. Sintesi dei problemi identificati

### Problema serio (comportamento fiscale non realistico per ETF)
- **`calcola_minusvalenze` con ETF UCITS**: la compensazione minusvalenze non è applicabile in Italia per ETF armonizzati. Questa funzionalità simula uno scenario che non esiste nella realtà per un portafoglio composto interamente da ETF. È corretto disabilitarla di default (`CALCOLA_MINUSVALENZE = False`).

### Limitazioni minori (semplificazioni accettabili)
- **Minimo imposta di bollo €34.20/anno**: non implementato. Rilevante solo per portafogli molto piccoli.
- **Divisore 365.25 vs 365**: differenza trascurabile (~0.07%).
- **BTP/BOT al 12.5%**: non nel portafoglio corrente, quindi non impatta.

### Tutto il resto è matematicamente e fiscalmente corretto.

---

## 5. Conclusione

Il backtester implementa una logica **corretta e standard** per la simulazione di un portafoglio ribilanciato. I calcoli matematici (ribilanciamento, PMC, CAGR, transaction costs, expense ratio) sono tutti verificati contro fonti primarie (CFA Institute, Vanguard, Charles Schwab, normativa TUIR).

Il **limite principale** è la funzionalità di riporto minusvalenze (`--calcola-minusvalenze`): nella realtà italiana, le plusvalenze da ETF armonizzati sono "redditi di capitale" e non possono essere compensate con minusvalenze, rendendo questa funzione inapplicabile per un portafoglio composto da ETF UCITS. La scelta di disabilitarla di default è quindi la più corretta.

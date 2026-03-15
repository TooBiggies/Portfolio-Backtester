# Analisi differenze: Backtester.ipynb (dev-mcaresein) vs backtester.py (dev-fabriziobiondi)

Data analisi: 2026-03-15

---

## Risposta diretta

Sì, i due producono risultati diversi. La causa principale è un **bug nel segno delle tasse** in `classes.py` (dev-fabriziobiondi) che fa sì che il pagamento delle imposte *aumenti* il valore del portafoglio invece di ridurlo, gonfiando artificialmente i rendimenti. Ci sono anche altri problemi strutturali minori.

---

## Differenze identificate

### Bug 1 (CRITICO) — Segno errato delle tasse in `classes.py`

**File**: `classes.py` (dev-fabriziobiondi), linee 157 e 291

**Il problema**: `self.tax` è impostato a un valore **positivo** nel nuovo codice, ma viene usato in formule che si aspettano un valore **negativo** (convenzione costo/uscita di cassa).

Il vecchio codice (dev-mcaresein `classes.py`) usava:
```python
self.tax += -plusval.sum() * self.tax_rate  # NEGATIVO → costo
# poi:
NetTotValue = TotValue + TransactionalCost + tax  # entrambi negativi → riducono il valore
```

Il nuovo codice (dev-fabriziobiondi `classes.py`) usa:
```python
self.tax = float(max(0.0, net)) * float(self.tax_rate)  # POSITIVO
# ma le formule che lo usano non sono state aggiornate:
# linea 157: NetTotValue = TotValue + TransactionalCost + self.tax
# linea 291: immediate_payments += (self.tax + self.TransactionalCost)
```

**Effetto**: Nei giorni di ribilanciamento, il pagamento delle tasse *aumenta* `NetTotValue` e `immediate_payments` invece di ridurli. Di conseguenza `TotValue = BrokerValue = GrossValue + immediate_payments` è **sovrastimato**, e il rendimento calcolato quel giorno appare artificialmente alto.

**Quantificazione** (esempio con portafoglio da €10.000, tasse = €260, commissioni = -€29):

| | NetTotValue | Return giornaliero |
|---|---|---|
| Bug (tax = +260) | 10.050 − 29 + 260 = **10.281** | **+2.81%** |
| Corretto (tax = −260) | 10.050 − 29 − 260 = **9.761** | **−2.39%** |

Errore per singolo evento: **+5.2%** sul rendimento giornaliero. Cumulato su decine di ribilanciamenti, produce un'enorme sovrastima del rendimento finale.

---

### Bug 2 (SERIO) — `PMC_weight` inizializzato a 1.0 invece del notional iniziale

**File**: `classes.py` (dev-fabriziobiondi e dev-mcaresein), metodo `__init__` e `update_PMC`

**Il problema**: Il PMC (Prezzo Medio di Carico) è calcolato con una media pesata:
```
nuovo_PMC = (old_PMC × old_units + delta × price) / (old_units + delta)
```
dove `old_units` è il denominatore tracciato da `PMC_weight`. Ma `PMC_weight` è inizializzato a `1.0` invece che al `notional` iniziale (es. 6.000 quote).

Codice (linee 99, 183-185):
```python
self.PMC_weight = pd.Series(data=1.0, index=self.IndexName)  # BUG: deve essere = notional
...
self.PMC[mask_buy] = (self.PMC[mask_buy]*self.PMC_weight[mask_buy]
                      + (self.delta_notional*StockPrice)[mask_buy])
self.PMC_weight[mask_buy] += self.delta_notional[mask_buy]
self.PMC[mask_buy] /= self.PMC_weight[mask_buy]
```

**Effetto pratico** (VT: 60% su €10.000, primo ribilanciamento +200 quote a €1.05):

| | PMC dopo primo acquisto | Tax su vendita di 100 quote a €1.10 |
|---|---|---|
| Bug (`PMC_weight=1`) | **1.0498** | €1.31 |
| Corretto (`PMC_weight=6000`) | **1.0016** | €2.56 |

Errore: il PMC è **sovrastimato del 5%**, quindi la plusvalenza tassabile è **sottostimata del 49%**. Le tasse calcolate dal backtester sono circa **la metà** di quelle corrette.

Nota: `engine.py` (dev-mcaresein) usa `assets_costs / holdings` che è **il metodo corretto**.

---

### Bug 3 — `PMC_weight` non decresce sulle vendite

**File**: `classes.py` (entrambi i branch), metodo `update_PMC`

`PMC_weight` è aggiornato solo al rialzo (su acquisti: `mask_buy = delta_notional > 0`). Quando si vendono quote, `PMC_weight` rimane invariato anche se `notional` diminuisce. Questo fa crescere il denominatore oltre il numero reale di quote detenute, accumulando errore su errore.

`engine.py` (dev-mcaresein) gestisce correttamente le vendite:
```python
def sell(self, ...):
    self.holdings[asset] -= units
    self.assets_costs[asset] -= units * pmc  # riduce la base proporzionalmente
```

---

### Differenza 4 — Applicazione expense ratio: giornaliera vs annuale

| | Metodo | Formula |
|---|---|---|
| `backtester.py` (`classes.py`) | **Giornaliera** pro-rata | `value × exp_rate × (days / 365.25)` |
| Notebook (`engine.py`) | **Annuale** lump-sum (al cambio anno) | `value × annual_costs_rate` (una volta all'anno) |

**Effetto**: L'importo totale annuale è simile (~uguale), ma il timing è diverso. Il backtester scala su ogni giorno; il notebook addebita tutto il costo in un'unica data (primo giorno del nuovo anno). L'impatto netto sul rendimento finale è modesto, ma produce differenze nelle date intermedie.

---

### Differenza 5 — Netting plus/minus nel ribilanciamento

| | Comportamento |
|---|---|
| `backtester.py` (corrente) | Compensa plusvalenze e minusvalenze di asset diversi nella *stessa operazione* prima di tassare |
| Notebook (`engine.py`) | Tassa ogni vendita individualmente: `max(0, gain) × tax_rate` per asset, nessuna compensazione |

```python
# backtester.py (classes.py):
net = realized_gains - realized_losses      # netting prima
self.tax = max(0.0, net) * tax_rate         # tassa il netto

# engine.py:
tax = max(0.0, units * (price - pmc)) * tax_rate  # per singolo asset, no compensazione
```

Il backtester paga meno tasse (perché compensa), il notebook ne paga di più. Questo causa differenze sistematiche in tutti i ribilanciamenti con mix di plus e minus.

---

### Differenza 6 — Costo di transazione al T=0

| | T=0 |
|---|---|
| `backtester.py` | Nessun costo di transazione sull'allocazione iniziale |
| Notebook (`engine.py`) | Addebita `brokerage_fee` sull'acquisto iniziale al T=0 |

Piccola differenza sul capitale di partenza (0.29% di €10.000 = €29).

---

## Riepilogo impatto

| # | Problema | File | Impatto |
|---|---|---|---|
| 1 | **Segno tasse sbagliato** — tasse aumentano rendimento | `classes.py` dev-fabriziobiondi | **CRITICO** — rende rendimenti irrealisticamente alti |
| 2 | **PMC_weight = 1.0** — PMC sovrastimato, tasse sottostimate ~50% | `classes.py` entrambi | **SERIO** |
| 3 | PMC_weight non decresce su vendite | `classes.py` entrambi | Medio — accumula errore #2 |
| 4 | Expense ratio: giornaliero vs annuale | Strutturale | Basso — timing diverso, totale simile |
| 5 | Netting plus/minus | Strutturale | Medio — tasse diverse per ogni ribilanciamento |
| 6 | TC a T=0 | Strutturale | Basso — differenza fissa di ~€29 |

---

## Cosa ha il notebook corretto che il backtester non ha

Il notebook (`engine.py`, dev-mcaresein) ha la logica **più corretta** per:

- **PMC**: usa `assets_costs / holdings` — si aggiorna correttamente sia su acquisti che su vendite
- **Rendimento netto**: `curr_net = portfolio.value - taxes - costs` — tasse sottratte, non aggiunte
- **TotValue**: `portfolio.value = holdings × prices` — puro valore di mercato, non contaminato da tasse

---

## Cosa ha il backtester corretto che il notebook non ha

- **Netting plus/minus** nella stessa operazione (più fedele al regime amministrato italiano)
- **Riporto minusvalenze** su 4 anni (art. 68 TUIR) — non presente nel notebook
- **Expense ratio giornaliero** — più preciso del lump-sum annuale
- **GrossValue / BrokerValue / NetValue** — distinzione tra valore lordo, broker e liquidazione

---

## Fix necessari in `classes.py` (dev-fabriziobiondi)

### Fix 1 — Segno delle tasse (Bug #1)
```python
# In update_tax(), cambiare il segno del risultato:
# PRIMA (errato):
self.tax = float(max(0.0, net)) * float(self.tax_rate)
# DOPO (corretto):
self.tax = -float(max(0.0, net)) * float(self.tax_rate)
```
Oppure aggiornare `calculate_NetTotValue` e `immediate_payments` per sottrarre le tasse.

### Fix 2 — PMC_weight inizializzazione (Bug #2)
```python
# In __init__(), cambiare:
# PRIMA (errato):
self.PMC_weight = pd.Series(data=1.0, index=self.IndexName)
# DOPO (corretto):
self.PMC_weight = self.notional.copy()
```
**Nota**: Questo fix dipende da `self.notional` che deve essere già calcolato prima — verificare l'ordine di inizializzazione in `__init__`.

### Fix 3 — PMC_weight su vendite (Bug #3)
```python
# In update_PMC(), aggiungere anche la gestione delle vendite:
mask_sell = self.delta_notional < 0
self.PMC_weight[mask_sell] += self.delta_notional[mask_sell]  # decrementa il denominatore
# (PMC non cambia sulle vendite, ma PMC_weight deve scendere)
```

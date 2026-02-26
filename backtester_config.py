"""Configurazione per il backtester: variabili estratte dalla UI del notebook.

Qui definiamo i pesi iniziali, il capitale e l'intervallo temporale usati
da `backtester.py`. Sotto è riportata anche una spiegazione breve di cosa
sono gli asset indicati (VT, SPY, ...), utile per riferimento.
"""

from datetime import date

# Asset weights in the same order as the notebook sliders:
# [VT, SPY, VXUS, GLD, CASH, SHY, IEF, TLT, ZROZ, KMLM, DBMF]
INITIAL_WEIGHTS = [0.60, 0.00, 0.00, 0.10, 0.00, 0.00, 0.00, 0.00, 0.25, 0.00, 0.05]

# Brief descriptions of the tickers used in the UI (for reference):
# - VT:    ETF azionario globale (esposizione a mercati sviluppati + emergenti)
# - SPY:   ETF S&P 500 (esposizione USA large-cap)
# - VXUS:  ETF azionario internazionale (esclude USA)
# - GLD:   ETF oro (esposizione al prezzo dell'oro)
# - CASH:  Liquidità / contanti
# - SHY:   ETF Treasury a breve termine (1-3 anni) — minor duration, minor volatilità
# - IEF:   ETF Treasury a medio termine (7-10 anni)
# - TLT:   ETF Treasury a lungo termine (20+ anni) — alta duration
# - ZROZ:  ETF/strumento Treasury a lunghissima scadenza (tipicamente zero-coupon) — duration molto elevata
# - KMLM:  Asset/ETF alternativo (simbolo locale; verificare il prodotto esatto nello sheet Timeseries)
# - DBMF:  Fondo/ETF multi-asset o strategia (simbolo locale; verificare il prodotto esatto nello sheet Timeseries)

# Initial capital (integer)
CAPITAL = 10000

# Start / end dates (datetime.date)
START_DATE = date(2020, 1, 1)
END_DATE = date(2025, 10, 30)

# Output filenames
OUTPUT_XLSX = "output_ptf.xlsx"
OUTPUT_DELTA_XLSX = "output_ptf_delta.xlsx"

# Portfolio parameters (extracted from the notebook/backtester.py)
# - transaction cost rate: commissioni + spread (fractional, e.g. 0.0029 = 0.29%)
TRANSAC_COST_RATE = 0.0029
# - expense rate: annual expense / tracking + bollo (fractional)
EXP_RATE = 0.002
# - tax rate on realized gains (fractional)
TAX_RATE = 0.26
# - rebalance threshold per-asset (absolute difference in weight)
REBALANCE_THRESHOLD = 0.05
# - whether to normalize stock prices at t0 (True/False)
STOCK_PRICE_NORMALIZATION = True

# Directory where markdown reports are written
REPORTS_DIR = "reports"

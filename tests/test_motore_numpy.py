"""Il motore numpy deve rifare i numeri di `backtester.backtest`, non avvicinarsi.

Il motore veloce esiste per calcolare griglie di migliaia di combinazioni, dove il
motore pandas impiega sedici secondi per simulazione. La tentazione è fidarsi perché
"i risultati sono simili": qui non basta. Ogni caso confronta la **serie giornaliera
del valore netto** e il **Sortino netto** con quelli prodotti da `backtest()`, e
fallisce se divergono oltre la tolleranza numerica del punto fisso di ribilanciamento.

Se un giorno le due implementazioni vengono divise, questi test sono la ragione per
cui non può succedere in silenzio.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import motore_numpy
from backtester import backtest

RADICE = Path(__file__).resolve().parent.parent
DATASET = str(RADICE / "Timeseries.csv")

# Periodo corto: il confronto deve girare in CI in pochi secondi, non in minuti.
INIZIO, FINE = "2010-01-01", "2015-12-31"

CASI = [
    ({"VTSIM": 0.6, "GLDSIM": 0.2, "TLTSIM": 0.2}, 0.05, 0.20),
    ({"VTSIM": 0.4, "GLDSIM": 0.3, "TLTSIM": 0.3}, 0.10, 0.20),
    ({"VTSIM": 0.8, "GLDSIM": 0.1, "TLTSIM": 0.1}, 0.05, None),
    ({"VTSIM": 0.0, "GLDSIM": 0.5, "TLTSIM": 0.5}, 0.05, 0.20),
]


def _prezzi(finestra=(INIZIO, FINE)):
    """Prezzi degli asset e tasso privo di rischio, allineati sulle stesse date."""
    df = pd.read_csv(DATASET, sep=";", encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    df = df[["VTSIM", "GLDSIM", "TLTSIM", "CASHX"]].apply(pd.to_numeric, errors="coerce").dropna()
    df = df[(df.index >= pd.Timestamp(finestra[0])) & (df.index <= pd.Timestamp(finestra[1]))]
    return df[["VTSIM", "GLDSIM", "TLTSIM"]], df["CASHX"].pct_change().fillna(0.0)


@pytest.mark.parametrize("pesi,soglia_assoluta,soglia_relativa", CASI)
def test_la_serie_netta_coincide_con_backtest(pesi, soglia_assoluta, soglia_relativa):
    prezzi, rf = _prezzi()
    vettore = np.array([pesi[n] for n in prezzi.columns], dtype=float)

    netti = motore_numpy.valori_netti(
        prezzi.to_numpy(dtype=float), vettore, soglia_assoluta=soglia_assoluta,
        soglia_relativa=soglia_relativa)

    log, _, _ = backtest(
        10_000.0, pesi, begin_date=pd.Timestamp(INIZIO), end_date=pd.Timestamp(FINE),
        brokerage_fee_rate=0.001, rebalance_threshold=soglia_assoluta, tax_rate=0.26,
        annual_costs_rate=0.002, risk_free_rate="CASHX", data_path=DATASET,
        save_outputs=False, plot=False, rel_rebalance_threshold=soglia_relativa)

    riferimento = log["Net"].to_numpy(dtype=float)
    assert len(netti) == len(riferimento)
    # Scarto relativo massimo sul valore giornaliero: il punto fisso del
    # ribilanciamento si ferma a 1e-8 di capitale, quindi un ordine di grandezza
    # sopra quella soglia sarebbe una differenza di logica, non di arrotondamento.
    scarto = np.max(np.abs(netti - riferimento)) / riferimento[0]
    assert scarto < 1e-6, f"scarto relativo massimo {scarto:.2e}"


@pytest.mark.parametrize("pesi,soglia_assoluta,soglia_relativa", CASI)
def test_il_sortino_netto_coincide(pesi, soglia_assoluta, soglia_relativa):
    prezzi, rf = _prezzi()
    vettore = np.array([pesi[n] for n in prezzi.columns], dtype=float)

    netti = motore_numpy.valori_netti(
        prezzi.to_numpy(dtype=float), vettore, soglia_assoluta=soglia_assoluta,
        soglia_relativa=soglia_relativa)
    sortino_veloce = motore_numpy.sortino_netto(netti, rf.to_numpy(dtype=float))

    _, _, riepilogo = backtest(
        10_000.0, pesi, begin_date=pd.Timestamp(INIZIO), end_date=pd.Timestamp(FINE),
        brokerage_fee_rate=0.001, rebalance_threshold=soglia_assoluta, tax_rate=0.26,
        annual_costs_rate=0.002, risk_free_rate="CASHX", data_path=DATASET,
        save_outputs=False, plot=False, rel_rebalance_threshold=soglia_relativa)
    atteso = riepilogo["risk_metrics"]["net"]["sortino"]

    assert sortino_veloce == pytest.approx(atteso, rel=1e-5, abs=1e-6)


def test_un_portafoglio_a_un_solo_asset_segue_il_prezzo():
    """Caso limite: senza ribilanciamenti il valore netto è il prezzo, meno costi e uscite."""
    prezzi, _ = _prezzi()
    solo = prezzi[["VTSIM"]].to_numpy(dtype=float)
    netti = motore_numpy.valori_netti(solo, np.array([1.0]), soglia_assoluta=0.05,
                                      commissione=0.0, costi_annui=0.0, imposta=0.0)
    atteso = 10_000.0 * solo[:, 0] / solo[0, 0]
    assert np.allclose(netti, atteso, rtol=0, atol=1e-6)


def test_senza_soglia_relativa_il_risultato_non_cambia_rispetto_a_prima():
    """`None` deve valere come "soglia relativa assente", non come zero."""
    prezzi, rf = _prezzi()
    vettore = np.array([0.6, 0.2, 0.2])
    a = motore_numpy.valori_netti(prezzi.to_numpy(float), vettore, soglia_assoluta=0.05,
                                  soglia_relativa=None)
    b = motore_numpy.valori_netti(prezzi.to_numpy(float), vettore, soglia_assoluta=0.05)
    assert np.array_equal(a, b)

# questi test leggono il dataset storico reale: senza Timeseries.csv si saltano
pytestmark = pytest.mark.dati

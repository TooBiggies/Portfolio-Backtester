"""Soglia di ribilanciamento relativa, in OR con quella assoluta.

La soglia assoluta misura lo scostamento in punti di peso: con 10 punti, un
comparto al 5% deve arrivare al 15% (o a -5%) prima di far scattare qualcosa.
La soglia relativa misura lo scostamento in percentuale del proprio peso
obiettivo: con il 50%, lo stesso comparto scatta al 7,5%. In OR basta una delle
due condizioni, quindi i comparti piccoli tornano a target prima di raddoppiare.
"""
import pandas as pd
import pytest

from engine import Portfolio, Rebalancer

PESI = {"A": 0.05, "B": 0.95}


def _portafoglio(pesi, prezzi_iniziali, prezzi_dopo, valore=1000.0):
    pf, _ = Portfolio.from_weights(
        pd.Series(prezzi_iniziali), valore, pesi, 0.0, 0.0)
    pf.prices = pd.Series(prezzi_dopo)
    return pf


def test_la_soglia_relativa_scatta_dove_quella_assoluta_no():
    """A scende da 5% a ~2,06%: 2,94 punti (sotto i 10 assoluti) ma 59% del peso."""
    pf = _portafoglio(PESI, {"A": 10.0, "B": 90.0}, {"A": 4.0, "B": 90.0})
    peso_prima = pf.weights["A"]
    assert peso_prima < 0.05

    # Solo soglia assoluta: 2,94 punti non bastano, nessun ribilanciamento.
    costi, tasse, delta = Rebalancer(dict(PESI), 0.10, tax_rate=0.0).rebalance(pf)
    assert sum(abs(v) for v in delta.values()) == 0.0
    assert abs(pf.weights["A"] - peso_prima) < 1e-12

    # Con la relativa al 50% scatta: lo scostamento e' il 58,8% del peso obiettivo.
    costi, tasse, delta = Rebalancer(dict(PESI), 0.10, tax_rate=0.0,
                                     rel_threshold=0.50).rebalance(pf)
    assert sum(abs(v) for v in delta.values()) > 0.0
    assert abs(pf.weights["A"] - 0.05) < 1e-9


def test_la_relativa_non_impedisce_lo_scatto_della_assoluta():
    """A al 68,75%: 18,75 punti superano la soglia assoluta, e il ribilanciamento avviene."""
    pf = _portafoglio({"A": 0.5, "B": 0.5}, {"A": 10.0, "B": 90.0}, {"A": 22.0, "B": 90.0})
    assert pf.weights["A"] > 0.68

    offsetto = Rebalancer({"A": 0.5, "B": 0.5}, 0.10, tax_rate=0.0,
                          rel_threshold=0.50).rebalance(pf)
    assert sum(abs(v) for v in offsetto[2].values()) > 0.0
    assert abs(pf.weights["A"] - 0.5) < 1e-9


def test_senza_soglia_relativa_il_comportamento_e_quello_di_prima():
    """rel_threshold=None deve coincidere con la sola soglia assoluta."""
    prezzi = {"A": 10.0, "B": 90.0}
    dopo = {"A": 4.0, "B": 90.0}

    pf_vecchio = _portafoglio(PESI, prezzi, dopo)
    pf_nuovo = _portafoglio(PESI, prezzi, dopo)
    vecchio = Rebalancer(dict(PESI), 0.10, tax_rate=0.0).rebalance(pf_vecchio)
    nuovo = Rebalancer(dict(PESI), 0.10, tax_rate=0.0, rel_threshold=None).rebalance(pf_nuovo)

    for serie_vecchia, serie_nuova in zip(vecchio, nuovo):
        for asset in PESI:
            assert serie_vecchia[asset] == pytest.approx(serie_nuova[asset], abs=1e-12)


def test_peso_obiettivo_nullo_non_divide_per_zero():
    """Un asset con peso obiettivo 0 non ha denominatore: resta sulla sola assoluta."""
    pf = _portafoglio({"A": 1.0, "B": 0.0}, {"A": 10.0, "B": 90.0}, {"A": 10.0, "B": 90.0})
    costi, tasse, delta = Rebalancer({"A": 1.0, "B": 0.0}, 0.10, tax_rate=0.0,
                                     rel_threshold=0.50).rebalance(pf)
    # B vale ~5,9% con peso obiettivo 0: la relativa non puo' scattare, e la
    # assoluta non e' superata. Nessuna eccezione, nessun ribilanciamento.
    assert sum(abs(v) for v in delta.values()) == 0.0

"""Blocca l'ordine reale dei valori di ritorno di Rebalancer.rebalance.

Nota: si passa una pd.Series (non un dict) perche' questo test deve essere
indipendente dalla correzione di fix/rebalancer-dict.
"""
import pandas as pd
from engine import Portfolio, Rebalancer


def test_ordine_dei_ritorni_e_costi_negativi():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                  {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 12.0, "B": 8.0})
    costs, taxes, deltas = Rebalancer(pd.Series({"A": 0.0, "B": 1.0}), 0.0001,
                                      tax_rate=0.26).rebalance(pf)
    assert all(v <= 0.0 for v in costs.values()), "costs deve essere negativo (uscita di cassa)"
    assert all(v <= 0.0 for v in taxes.values()), "taxes deve essere negativo (uscita di cassa)"
    assert deltas["A"] < 0 and deltas["B"] > 0, "deltas: positivo = acquisto"


def test_nessun_ribilanciamento_restituisce_zeri():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 1000, {"A": 1.0}, 0.0, 0.0)
    costs, taxes, deltas = Rebalancer(pd.Series({"A": 1.0}), 0.1, tax_rate=0.26).rebalance(pf)
    assert sum(costs.values()) == 0.0 and sum(taxes.values()) == 0.0

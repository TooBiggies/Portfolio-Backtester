"""Rebalancer documenta 'pd.Series or dict': il dict deve funzionare."""
import pandas as pd
from engine import Portfolio, Rebalancer


def test_rebalancer_accetta_un_dict():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                  {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 12.0, "B": 8.0})
    costs, taxes, deltas = Rebalancer({"A": 0.0, "B": 1.0}, 0.0001, tax_rate=0.26).rebalance(pf)
    assert abs(pf.weights["A"]) < 1e-9
    assert abs(pf.weights["B"] - 1.0) < 1e-9

"""Test di caratterizzazione del motore: fissano il comportamento attuale di engine.py.

Servono come rete di sicurezza per le correzioni successive: se un numero cambia,
deve essere per la ragione dichiarata nel test, non per caso.
"""
import pandas as pd
import pytest

from backtester import backtest
from engine import Portfolio, Rebalancer

W = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}


def test_ribilanciamento_riporta_ai_pesi_target():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                  {"A": 0.6, "B": 0.4}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 20.0, "B": 10.0})      # A sovrappesato
    Rebalancer(pd.Series({"A": 0.6, "B": 0.4}), 0.01, tax_rate=0.0).rebalance(pf)
    assert abs(pf.weights["A"] - 0.6) < 1e-9
    assert abs(pf.weights["B"] - 0.4) < 1e-9


def test_pmc_e_costo_medio_dopo_la_vendita():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 10.0})
    pf.buy(10.0, "A", 50)                               # 150 quote a PMC 10
    pf.sell(10.0, "A", 50, tax_rate=0.0)
    assert abs(pf.pmc["A"] - 10.0) < 1e-9
    assert abs(pf.holdings["A"] - 100.0) < 1e-9
    assert abs(pf.assets_costs["A"] - 1000.0) < 1e-9


def test_costo_di_transazione_presente_al_giorno_zero():
    # Convenzione dei costi: negativi (uscita di cassa).
    _, fees = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0029, 0.0)
    assert fees["A"] < 0.0
    assert abs(fees["A"]) > 0.0


def test_cagr_coerente_col_fattore_composto():
    _, _, s = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), save_outputs=False)
    atteso = (s["final_broker"] / 10000) ** (1 / s["years"]) - 1
    assert abs(s["cagr_broker"] - atteso) < 5e-3


def test_save_outputs_false_non_scrive_file(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("con save_outputs=False non deve essere scritto alcun file")
    monkeypatch.setattr(pd.DataFrame, "to_excel", boom)
    monkeypatch.setattr(pd.DataFrame, "to_csv", boom)
    backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
             end_date=pd.Timestamp("2020-03-02"), save_outputs=False)


def test_configurazione_di_default_converge():
    _, _, s = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0029,
                       annual_costs_rate=0.002, tax_rate=0.26, save_outputs=False)
    assert s["final_broker"] > 0 and s["final_gross"] > s["final_net"]

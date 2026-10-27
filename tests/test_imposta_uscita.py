"""Il valore netto deve usare l'aliquota configurata, non un 26% cablato."""
import pandas as pd
from backtester import backtest
from engine import Portfolio

W = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}


def test_aliquota_zero_netto_uguale_al_lordo():
    _, _, s = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0,
                       annual_costs_rate=0.0, tax_rate=0.0, save_outputs=False)
    assert abs(s["final_net"] - s["final_broker"]) < 1e-6, (
        f"con aliquota 0 il netto deve coincidere col broker: {s['final_net']} vs {s['final_broker']}")


def test_aliquota_piu_alta_netto_piu_basso():
    _, _, a = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), tax_rate=0.26, save_outputs=False)
    _, _, b = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), tax_rate=0.50, save_outputs=False)
    assert b["final_net"] < a["final_net"]


def test_cash_out_costs_usa_aliquota_del_portafoglio():
    # 100 quote comprate a 10, prezzo a 20: plusvalenza latente 1.000
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.0, tax_rate=0.10)
    pf.prices = pd.Series({"A": 20.0})
    assert abs(pf.cash_out_costs().sum() - 100.0) < 1e-9     # 10% di 1.000
    assert abs(pf.cash_out_costs(tax_rate=0.26).sum() - 260.0) < 1e-9   # override esplicito

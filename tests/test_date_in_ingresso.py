"""backtest() documenta date come stringhe: devono funzionare quanto i Timestamp."""
import pandas as pd
from backtester import backtest

W = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}


def test_date_come_stringhe():
    _, _, s = backtest(10000, W, begin_date="2020-01-02", end_date="2021-01-04", save_outputs=False)
    assert s["years"] > 0.9


def test_stringhe_e_timestamp_danno_lo_stesso_risultato():
    _, _, a = backtest(10000, W, begin_date="2020-01-02", end_date="2021-01-04", save_outputs=False)
    _, _, b = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), save_outputs=False)
    assert abs(a["final_broker"] - b["final_broker"]) < 1e-9

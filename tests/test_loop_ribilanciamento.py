"""Il ciclo di convergenza non deve poter girare all'infinito."""
import time
import pandas as pd
import pytest
from backtester import backtest


def test_prezzi_mancanti_all_inizio_fallisce_subito_e_con_messaggio_chiaro():
    t0 = time.time()
    with pytest.raises((ValueError, RuntimeError), match="prezzo valido|non finito|non converge|non coperta"):
        backtest(10000, {"KMLMSIM": 1.0}, begin_date=pd.Timestamp("1990-01-02"),
                 end_date=pd.Timestamp("1991-01-02"), save_outputs=False)
    assert time.time() - t0 < 5, "deve fallire subito, non ciclare"


def test_un_backtest_normale_converge():
    _, _, s = backtest(10000, {"VTSIM": 0.6, "GLDSIM": 0.4}, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), save_outputs=False)
    assert s["final_broker"] > 0

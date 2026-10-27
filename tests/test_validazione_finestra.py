"""Una finestra non coperta da tutti gli asset deve fallire in modo esplicito."""
import pandas as pd
import pytest
from backtester import backtest


def test_finestra_non_coperta_errore_esplicito():
    # KMLMSIM non ha prezzi prima del 2000-01-03: chiedere il 1990 non e' valido.
    with pytest.raises(ValueError, match="non coperta"):
        backtest(10000, {"VTSIM": 0.5, "KMLMSIM": 0.5}, begin_date=pd.Timestamp("1990-01-02"),
                 end_date=pd.Timestamp("1991-01-02"), save_outputs=False)


def test_asset_a_peso_zero_non_blocca():
    # KMLMSIM a peso 0: i suoi NaN non devono impedire la simulazione.
    _, _, s = backtest(10000, {"VTSIM": 1.0, "KMLMSIM": 0.0},
                       begin_date=pd.Timestamp("1990-01-02"),
                       end_date=pd.Timestamp("1993-01-04"), save_outputs=False)
    assert s["final_broker"] > 0


def test_finestra_valida_passa():
    _, _, s = backtest(10000, {"VTSIM": 0.6, "KMLMSIM": 0.4},
                       begin_date=pd.Timestamp("2010-01-04"),
                       end_date=pd.Timestamp("2011-01-04"), save_outputs=False)
    assert s["final_broker"] > 0

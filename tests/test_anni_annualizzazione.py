"""Il CAGR deve essere annualizzato sui dati realmente simulati, non sulle date richieste."""
import pandas as pd
from backtester import backtest


def test_anni_usano_lo_span_reale_dei_dati():
    # VTSIM parte il 31/12/1969: chiedendo il 1960 la finestra richiesta (65,66 anni)
    # non coincide con quella simulata (55,68 anni).
    _, _, s = backtest(10000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("1960-01-02"),
                       end_date=pd.Timestamp("2025-09-01"), save_outputs=False)
    assert 55.0 < s["years"] < 56.5, f"anni dichiarati: {s['years']}"
    assert s["cagr_gross"] > 0.09, f"CAGR lordo: {s['cagr_gross']:.4f}"

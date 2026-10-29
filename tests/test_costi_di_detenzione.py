"""I costi di detenzione: chi non ne ha non deve pagarli, e 0,2% annuo e' 0,2%.

Dal #73 l'imposta di bollo non e' piu' un parametro separato: e' un costo annuo di
detenzione, quello che l'interfaccia mostra nel campo "Costi annui" (default 0,2%).
Quindi `annual_costs_rate=0` deve valere zero davvero, anche per il portafoglio ideale.
"""
import warnings

import pandas as pd
import pytest

from backtester import backtest
from engine import Portfolio


def test_portafoglio_ideale_senza_costi():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.0)
    assert float(pf.daily_annual_costs.sum()) == 0.0
    h = pf.holdings.copy()
    pf.apply_holding_costs()
    assert (pf.holdings == h).all(), "senza costi annui le quote non devono cambiare"


def test_costi_annui_dello_0_2_per_anno_tolgono_lo_0_2_per_anno():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.002)
    quota = float(pf.daily_annual_costs.sum()) / pf.broker_assets_value * 252
    assert abs(quota - 0.002) < 1e-9, f"costo annuo effettivo: {quota}"


def test_il_costo_annuo_non_si_puo_contare_due_volte():
    """Il difetto che il #73 chiude: bollo separato + 0,2% nel campo costi annui
    faceva pagare lo 0,4% l'anno. Ora c'e' un solo campo, quindi lo 0,2% scritto
    dall'utente e' lo 0,2% pagato."""
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.002)
    quota = float(pf.daily_annual_costs.sum()) / pf.broker_assets_value * 252
    assert quota < 0.003, f"drag di detenzione {quota}: il bollo e' contato due volte"
    assert not hasattr(pf, "bollo")


def test_lordo_uguale_a_buy_and_hold_senza_costi():
    _, _, s = backtest(10000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0,
                       annual_costs_rate=0.0, tax_rate=0.0, save_outputs=False)
    df = pd.read_csv("./Timeseries.csv", sep=";")
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    df = df[(df["Date"] >= pd.Timestamp("2020-01-02")) & (df["Date"] <= pd.Timestamp("2021-01-04"))]
    atteso = 10000 * df["VTSIM"].iloc[-1] / df["VTSIM"].iloc[0]
    assert abs(s["final_gross"] - atteso) / atteso < 1e-9, f"lordo {s['final_gross']} vs buy&hold {atteso}"


# ---------------------------------------------------------------------------
# Retrocompatibilita' del parametro `bollo_rate` (chi scriveva codice prima del #73)
# ---------------------------------------------------------------------------

def test_bollo_rate_esplicito_da_gli_stessi_numeri_dei_costi_annui():
    """Chi passa ancora bollo_rate=0.002 deve ottenere esattamente quello che ottiene
    chi mette 0,002 nei costi annui: nessuno deve riscrivere le proprie chiamate."""
    vecchia = backtest(10000, {"VTSIM": 0.6, "ZROZSIM": 0.4}, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0029,
                       annual_costs_rate=0.0, bollo_rate=0.002, tax_rate=0.26,
                       save_outputs=False)[2]
    nuova = backtest(10000, {"VTSIM": 0.6, "ZROZSIM": 0.4}, begin_date=pd.Timestamp("2020-01-02"),
                     end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0029,
                     annual_costs_rate=0.002, tax_rate=0.26, save_outputs=False)[2]
    assert vecchia["final_broker"] == pytest.approx(nuova["final_broker"], rel=1e-12)


def test_bollo_rate_avvisa_che_e_deprecato():
    with pytest.warns(DeprecationWarning, match="bollo_rate"):
        Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.0, bollo_rate=0.002)


def test_senza_bollo_rate_non_si_paga_il_bollo():
    """Il caso nuovo: il bollo sta nei costi annui, quindi non passare `bollo_rate`
    deve valere zero, non 0,2% di default."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)   # nessun avviso se non lo si passa
        pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.0)
    assert float(pf.daily_annual_costs.sum()) == 0.0

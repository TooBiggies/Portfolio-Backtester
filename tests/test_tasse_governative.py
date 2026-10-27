"""Fiscalita' delle obbligazioni: quota white list tassata al 12,5%.

Regola: sulla quota di titoli di Stato white list la base imponibile e' ridotta al 48,08%
e l'aliquota effettiva e' 12,5% (art. 2 D.L. 138/2011, D.M. 13/12/2011, circ. 19/E/2014).
Sul resto si applica il 26%. La percentuale e' certificata dall'emittente e va dichiarata
per asset: qui e' il parametro `gov_share`.

Attenzione: i Treasury USA sono white list, quindi un ETF su Treasury ha la stessa
aliquota effettiva di un governativo euro.
"""
import pandas as pd
import pytest

from engine import Portfolio, Rebalancer


def portafoglio(asset="GOV", prezzo=10.0, gov_share=None, tax_rate=0.26):
    """100 quote comprate a 10 (capitale 1000, PMC 10)."""
    pf, _ = Portfolio.from_weights(pd.Series({asset: prezzo}), 1000, {asset: 1.0}, 0.0, 0.0,
                                   tax_rate=tax_rate, gov_share=gov_share)
    return pf


def test_lordo_indipendente_dai_parametri_fiscali():
    """Il portafoglio ideale non paga imposte: il lordo non deve muoversi al variare di
    aliquota, quota white list, commissioni o costi annui.

    Regressione: il portafoglio ideale riceveva gov_share con tax_rate=0, quindi il 12,5%
    sulla quota veniva addebitato anche nel run a costi zero e il lordo scendeva da
    37.388,49 a 36.688,50 (Treasury al 100%) e a 36.521,06 (quota 20% su VTSIM).
    """
    from backtester import backtest

    pesi = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}
    base = dict(initial_value=10000, weights=pesi,
                begin_date=pd.Timestamp("2010-01-02"), end_date=pd.Timestamp("2025-09-01"),
                save_outputs=False)
    configurazioni = [
        dict(tax_rate=0.0, gov_share={}),
        dict(tax_rate=0.26, gov_share={}),
        dict(tax_rate=0.26, gov_share={"SHYSIM": 1.0, "IEFSIM": 1.0, "TLTSIM": 1.0, "ZROZSIM": 1.0}),
        dict(tax_rate=0.26, gov_share={"VTSIM": 0.2, "ZROZSIM": 1.0}),
        dict(tax_rate=0.26, gov_share={"ZROZSIM": 1.0}, brokerage_fee_rate=0.0029),
        dict(tax_rate=0.26, gov_share={"ZROZSIM": 1.0}, annual_costs_rate=0.002),
    ]
    lordi = [backtest(**base, **cfg)[2]["final_gross"] for cfg in configurazioni]
    assert lordi == pytest.approx([lordi[0]] * len(lordi), rel=0, abs=1e-6), lordi


def test_aliquota_effettiva_per_quota_white_list():
    pf = portafoglio(gov_share={"GOV": 1.0})
    assert pf.tax_rate_for("GOV") == pytest.approx(0.125, abs=1e-12)
    # quota mista: 26% - 13,5 x quota
    pf.gov_share = {"GOV": 0.4}
    assert pf.tax_rate_for("GOV") == pytest.approx(0.206, abs=1e-12)
    # nessuna quota dichiarata -> 26% pieno
    assert portafoglio().tax_rate_for("GOV") == pytest.approx(0.26, abs=1e-12)


def test_la_riduzione_al_48_08_per_cento_equivale_al_12_5():
    # la norma riduce la base, non l'aliquota: 48,08% x 26% = 12,5%
    # 48,08% e' la cifra pubblicata, arrotondata: 0,4808 x 26% = 12,5008%
    assert 0.4808 * 0.26 == pytest.approx(0.125, abs=1e-5)


def test_quota_fuori_range_viene_limitata():
    pf = portafoglio(gov_share={"GOV": 1.5})
    assert pf.tax_rate_for("GOV") == pytest.approx(0.125, abs=1e-12)
    pf.gov_share = {"GOV": -0.3}
    assert pf.tax_rate_for("GOV") == pytest.approx(0.26, abs=1e-12)
    pf.gov_share = {"GOV": "non un numero"}
    assert pf.tax_rate_for("GOV") == pytest.approx(0.26, abs=1e-12)


def test_vendita_di_un_governativo_paga_il_12_5():
    pf = portafoglio(gov_share={"GOV": 1.0})
    pf.prices = pd.Series({"GOV": 20.0})           # +100 di plusvalenza per 10 quote
    fee, tax = pf.sell(20.0, "GOV", 10)
    assert tax == pytest.approx(10 * (20 - 10) * 0.125, abs=1e-12)   # 12,50


def test_vendita_di_un_azionario_paga_il_26():
    pf = portafoglio(asset="EQ")
    pf.prices = pd.Series({"EQ": 20.0})
    fee, tax = pf.sell(20.0, "EQ", 10)
    assert tax == pytest.approx(10 * (20 - 10) * 0.26, abs=1e-12)    # 26,00


def test_stessa_operazione_governativo_contro_azionario():
    gov = portafoglio("GOV", gov_share={"GOV": 1.0})
    eq = portafoglio("EQ")
    gov.prices = pd.Series({"GOV": 20.0}); eq.prices = pd.Series({"EQ": 20.0})
    _, tassa_gov = gov.sell(20.0, "GOV", 10)
    _, tassa_eq = eq.sell(20.0, "EQ", 10)
    assert tassa_gov / tassa_eq == pytest.approx(0.125 / 0.26, rel=1e-12)   # 0,4808


def test_rebalancer_usa_l_aliquota_dell_asset_non_un_tasso_unico():
    pf, _ = Portfolio.from_weights(pd.Series({"GOV": 10.0, "EQ": 10.0}), 1000,
                                   {"GOV": 0.5, "EQ": 0.5}, 0.0, 0.0,
                                   gov_share={"GOV": 1.0})
    pf.prices = pd.Series({"GOV": 20.0, "EQ": 10.0})   # il governativo e' salito
    costs, taxes, deltas = Rebalancer(pd.Series({"GOV": 0.5, "EQ": 0.5}), 0.01).rebalance(pf)
    plusvalenza_gov = -float(deltas["GOV"]) / 20.0 * (20.0 - 10.0)
    assert -float(taxes["GOV"]) == pytest.approx(0.125 * plusvalenza_gov, rel=1e-9)
    assert -float(taxes["EQ"]) == 0.0


def test_cash_out_costs_per_asset():
    pf, _ = Portfolio.from_weights(pd.Series({"GOV": 10.0, "EQ": 10.0}), 1000,
                                   {"GOV": 0.5, "EQ": 0.5}, 0.0, 0.0,
                                   gov_share={"GOV": 1.0})
    pf.prices = pd.Series({"GOV": 20.0, "EQ": 20.0})   # +500 di gain su ciascuno
    costi = pf.cash_out_costs()
    assert float(costi["GOV"]) == pytest.approx(500 * 0.125, abs=1e-9)    # 62,50
    assert float(costi["EQ"]) == pytest.approx(500 * 0.26, abs=1e-9)      # 130,00


def test_override_esplicito_prevale_sulla_quota():
    pf = portafoglio(gov_share={"GOV": 1.0})
    pf.prices = pd.Series({"GOV": 20.0})
    _, tax = pf.sell(20.0, "GOV", 10, tax_rate=0.26)
    assert tax == pytest.approx(26.0, abs=1e-12)

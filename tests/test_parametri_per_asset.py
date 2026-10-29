"""Parametri di costo per singolo strumento (issue #73).

Tre regole che il motore deve rispettare, verificate qui:

1. **Compatibilita'**: uno scalare e un dict con lo stesso valore su tutti gli asset
   devono produrre numeri identici. Se non e' cosi', il passaggio ai parametri per
   asset ha cambiato il modello invece di generalizzarlo.
2. **Effetto per asset**: cambiare il parametro di un solo asset deve cambiare il
   risultato in modo coerente (chi paga meno costi tiene piu' capitale).
3. **Una sola verita' fiscale**: l'aliquota esplicita per asset vince sulla quota
   white list, e i due modi devono coincidere quando dicono la stessa cosa
   (12,5% esplicito sui Treasury == gov_share 100%).
"""
import pandas as pd
import pytest

from backtester import backtest
from engine import Portfolio, per_asset

INIZIO = pd.Timestamp("2020-01-02")
FINE = pd.Timestamp("2021-01-04")
PESI = {"VTSIM": 0.6, "ZROZSIM": 0.4}


def esegui(**kwargs):
    return backtest(10000, PESI, begin_date=INIZIO, end_date=FINE, save_outputs=False, **kwargs)[2]


# ---------------------------------------------------------------- per_asset()

def test_per_asset_accetta_scalare_dict_e_series():
    indice = pd.Index(["A", "B"])
    assert list(per_asset(0.01, indice)) == [0.01, 0.01]
    assert list(per_asset({"A": 0.01}, indice)) == [0.01, 0.0]        # B assente -> default
    assert list(per_asset({"A": 0.01}, indice, default=0.26)) == [0.01, 0.26]
    serie = pd.Series({"B": 0.05}, dtype="float64")
    assert list(per_asset(serie, indice)) == [0.0, 0.05]              # riallineata all'indice
    assert list(per_asset(None, indice, default=0.2)) == [0.2, 0.2]


# ------------------------------------------------------- 1. compatibilita'

def test_commissione_scalare_e_dict_uniforme_danno_gli_stessi_numeri():
    scalare = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    uniforme = esegui(brokerage_fee_rate={"VTSIM": 0.0029, "ZROZSIM": 0.0029},
                      annual_costs_rate=0.002, tax_rate=0.26)
    for chiave in ("final_gross", "final_broker", "final_net", "cagr_net"):
        assert scalare[chiave] == pytest.approx(uniforme[chiave], rel=1e-12), chiave


def test_costi_annui_scalari_e_per_asset_uniformi_danno_gli_stessi_numeri():
    scalare = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    uniforme = esegui(brokerage_fee_rate=0.0029,
                      annual_costs_rate={"VTSIM": 0.002, "ZROZSIM": 0.002}, tax_rate=0.26)
    assert scalare["final_net"] == pytest.approx(uniforme["final_net"], rel=1e-12)


# -------------------------------------------------------- 2. effetto per asset

def test_commissione_di_un_solo_asset_cambia_il_risultato():
    uniforme = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.0, tax_rate=0.0)
    per_asset_ = esegui(brokerage_fee_rate={"VTSIM": 0.0, "ZROZSIM": 0.05},
                        annual_costs_rate=0.0, tax_rate=0.0)
    assert per_asset_["final_broker"] != pytest.approx(uniforme["final_broker"], rel=1e-9)


def test_commissione_zero_su_entrambi_vale_buy_and_hold():
    """Con commissione 0 per asset il broker deve valere esattamente il buy and hold:
    e' la prova che il parametro arriva davvero al posto giusto (se restasse uno
    scalare di comodo, questo test passerebbe lo stesso... ma il precedente no)."""
    zero = esegui(brokerage_fee_rate={"VTSIM": 0.0, "ZROZSIM": 0.0},
                  annual_costs_rate=0.0, tax_rate=0.0, rebalance_threshold=1.0)
    scalare = esegui(brokerage_fee_rate=0.0, annual_costs_rate=0.0, tax_rate=0.0,
                     rebalance_threshold=1.0)
    assert zero["final_broker"] == pytest.approx(scalare["final_broker"], rel=1e-12)


def test_costi_annui_piu_alto_su_un_asset_riduce_il_valore():
    leggero = esegui(brokerage_fee_rate=0.0, annual_costs_rate={"VTSIM": 0.001, "ZROZSIM": 0.001},
                     tax_rate=0.0)
    pesante = esegui(brokerage_fee_rate=0.0, annual_costs_rate={"VTSIM": 0.02, "ZROZSIM": 0.001},
                     tax_rate=0.0)
    assert pesante["final_broker"] < leggero["final_broker"]


# ------------------------------------------------------- 3. verita' fiscale

def test_aliquota_esplicita_vince_sulla_quota_white_list():
    pf = Portfolio(prices=pd.Series({"BOND": 100.0}), initial_value=1000,
                   tax_rate={"BOND": 0.26}, gov_share={"BOND": 1.0})
    assert pf.tax_rate_for("BOND") == pytest.approx(0.26)


def test_senza_aliquota_esplicita_la_quota_white_list_vale_ancora():
    """Retrocompatibilita': finche' l'interfaccia passa uno scalare + gov_share,
    il 12,5% sui titoli di Stato si calcola come prima."""
    pf = Portfolio(prices=pd.Series({"BOND": 100.0, "EQUITY": 50.0}), initial_value=1000,
                   tax_rate=0.26, gov_share={"BOND": 1.0})
    assert pf.tax_rate_for("BOND") == pytest.approx(0.125)
    assert pf.tax_rate_for("EQUITY") == pytest.approx(0.26)


def test_dodici_cinque_per_cento_esplicito_equivale_alla_quota_white_list():
    """La prova che serve prima di togliere la sezione "quota white list" dalla UI:
    dire 12,5% a mano sui Treasury deve dare gli stessi numeri di gov_share=100%."""
    con_quota = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26,
                       gov_share={"ZROZSIM": 1.0})
    esplicita = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002,
                       tax_rate={"VTSIM": 0.26, "ZROZSIM": 0.125})
    assert esplicita["final_net"] == pytest.approx(con_quota["final_net"], rel=1e-12)
    assert esplicita["cagr_net"] == pytest.approx(con_quota["cagr_net"], rel=1e-12)


def test_aliquota_al_26_su_tutto_costa_piu_del_dodici_cinque_sui_bond():
    """Il numero che giustifica il default 12,5% sui Treasury: portarli al 26% non e'
    una preferenza, costa. Qui la differenza deve essere negativa e non nulla."""
    pro_quota = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002,
                       tax_rate={"VTSIM": 0.26, "ZROZSIM": 0.125})
    piatta = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002,
                    tax_rate={"VTSIM": 0.26, "ZROZSIM": 0.26})
    assert piatta["final_net"] < pro_quota["final_net"]

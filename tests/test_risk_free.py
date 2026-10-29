"""Tasso privo di rischio: scalare storico, oppure una serie del dataset (issue #79).

Le tre cose da garantire, in ordine di importanza:

1. **Nessuna regressione**: con uno scalare i numeri devono essere identici a quelli
   prodotti prima che esistesse la forma per serie. E' il vincolo che rende la modifica
   approvabile senza ricontrollare ogni report.
2. **Equivalenza dichiarata**: se il tasso e' costante e pari alla media della serie,
   il risultato deve coincidere con quello per periodo — altrimenti la differenza fra i
   due metodi sarebbe una scelta nascosta, non un'implementazione.
3. **Effetto reale**: con CASHX lo Sharpe e il Sortino calano, la volatilita' e il CAGR
   no. Le metriche di rischio cambiano, quelle di rendimento non devono muoversi.
"""
import math

import pandas as pd
import pytest

from backtester import backtest, serie_da_dataset
from metrics import risk_free_daily, risk_metrics

PESI = {"VTSIM": 0.6, "ZROZSIM": 0.4}
INIZIO = pd.Timestamp("2015-01-02")
FINE = pd.Timestamp("2021-01-04")


def esegui(**kwargs):
    return backtest(10000, PESI, begin_date=INIZIO, end_date=FINE, save_outputs=False, **kwargs)


def serie_valori(n=260):
    """Serie con oscillazioni regolari: serve solo ad avere rendimenti non nulli."""
    indice = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series([100.0 * (1.0004 ** i) * (1 + 0.01 * math.sin(i / 3)) for i in range(n)],
                     index=indice, dtype="float64")


# ------------------------------------------------- 1. nessuna regressione

def test_con_rf_zero_le_metriche_sono_quelle_di_sempre():
    """Riproduce a mano la formula storica e la confronta con la nuova implementazione."""
    valori = serie_valori()
    rets = (valori / valori.shift(1) - 1).dropna()
    # I periodi per anno si deducono dalle date: su una serie sintetica di 260 giorni di
    # borsa valgono ~261, non 252 (259 intervalli su 0,99 anni di calendario). Cablare
    # 252 qui faceva sembrare sbagliata l'implementazione.
    ppy = risk_metrics(valori)["periods_per_year"]
    vol = float(rets.std(ddof=1)) * math.sqrt(ppy)
    sharpe_atteso = float(rets.mean()) * ppy / vol
    downside = rets.clip(upper=0.0)
    sortino_atteso = float(rets.mean()) * ppy / (
        float((downside ** 2).mean() ** 0.5) * math.sqrt(ppy))

    m = risk_metrics(valori, risk_free_rate=0.0)
    assert m["sharpe"] == pytest.approx(sharpe_atteso, rel=1e-12)
    assert m["sortino"] == pytest.approx(sortino_atteso, rel=1e-12)
    assert m["volatility"] == pytest.approx(vol, rel=1e-12)
    assert m["risk_free_mean"] == 0.0


def test_con_rf_costante_il_risultato_e_quello_della_formula_storica():
    """Con un tasso scalare la versione per periodo deve coincidere con
    ``mean(r)*ppy - rf`` diviso la volatilita' dei rendimenti."""
    valori = serie_valori()
    rets = (valori / valori.shift(1) - 1).dropna()
    ppy, rf = risk_metrics(valori)["periods_per_year"], 0.02
    vol = float((rets - rf / ppy).std(ddof=1)) * math.sqrt(ppy)
    sharpe_atteso = (float(rets.mean()) * ppy - rf) / vol
    assert risk_metrics(valori, risk_free_rate=rf)["sharpe"] == pytest.approx(sharpe_atteso, rel=1e-12)


# ------------------------------------------------- 2. equivalenza dichiarata

def test_rf_costante_pari_alla_media_della_serie_coincide_col_per_periodo():
    """La differenza fra 'rf costante' e 'rf per periodo' e' zero al sesto decimale:
    il tasso a breve si muove lentissimo rispetto al portafoglio. Se un giorno non fosse
    piu' cosi', questa asserzione lo direbbe."""
    valori = serie_valori()
    rets = (valori / valori.shift(1) - 1).dropna()
    ppy = risk_metrics(valori)["periods_per_year"]
    rf_giornaliero = pd.Series(0.00005, index=rets.index)      # costante per costruzione
    per_periodo = risk_metrics(valori, risk_free_rate=rf_giornaliero)
    scalare = risk_metrics(valori, risk_free_rate=0.00005 * ppy)   # stesso tasso annuo
    assert per_periodo["sharpe"] == pytest.approx(scalare["sharpe"], rel=1e-12)


def test_risk_free_daily_allinea_e_riempie_con_zero():
    indice = pd.bdate_range("2020-01-01", periods=3)
    serie = pd.Series([0.001, 0.002], index=indice[:2])          # manca l'ultimo giorno
    rf = risk_free_daily(serie, indice, 252)
    assert list(rf) == [0.001, 0.002, 0.0]                        # il tasso non si trascina
    assert list(risk_free_daily(0.0252, indice, 252)) == [0.0001] * 3


# ------------------------------------------------- 3. effetto reale

def test_cashx_abbassa_sharpe_e_sortino_ma_non_il_rendimento():
    senza = esegui(risk_free_rate=0.0)
    con = esegui(risk_free_rate="CASHX")
    m_senza, m_con = senza[2]["risk_metrics"]["net"], con[2]["risk_metrics"]["net"]

    assert m_con["sharpe"] < m_senza["sharpe"], "lo Sharpe con rf>0 deve essere piu' basso"
    assert m_con["sortino"] < m_senza["sortino"], "il Sortino usa lo stesso target"
    assert m_con["volatility"] == pytest.approx(m_senza["volatility"], rel=1e-12)
    assert senza[2]["final_net"] == pytest.approx(con[2]["final_net"], rel=1e-12)
    for chiave in ("cagr_net", "cagr_broker", "cagr_gross"):
        assert senza[2][chiave] == pytest.approx(con[2][chiave], rel=1e-12), chiave


def test_il_riepilogo_dichiara_il_tasso_usato():
    _, _, con = esegui(risk_free_rate="CASHX")
    _, _, senza = esegui(risk_free_rate=0.0)
    assert con["risk_free_rate_source"] == "CASHX"
    assert senza["risk_free_rate_source"] == "0"
    assert con["risk_free_rate"] > 0.005, "nel 2015-2021 il cash ha reso piu' di mezzo punto"
    assert senza["risk_free_rate"] == 0.0


# ------------------------------------------------- errori parlanti

def test_colonna_inesistente_elenca_quelle_disponibili():
    with pytest.raises(ValueError, match="assente dal dataset"):
        esegui(risk_free_rate="NONESISTE")


def test_serie_che_non_copre_la_finestra_solleva_errore():
    """Un tasso che sparisce per un pezzo di finestra abbasserebbe lo Sharpe senza dirlo:
    meglio un errore che un numero sbagliato e plausibile."""
    df = pd.DataFrame({"Date": ["02/01/2020", "03/01/2020"], "CASHX": [100.0, 100.1]})
    date = pd.bdate_range("2020-01-02", periods=4)
    with pytest.raises(ValueError, match="non copre la finestra"):
        serie_da_dataset(df, "CASHX", date)

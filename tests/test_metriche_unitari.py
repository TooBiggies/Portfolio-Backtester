"""Test unitari delle metriche di rischio su serie costruite a mano.

Ogni valore atteso e' calcolato a mano nella docstring: se il test fallisce si
vede subito se il bug e' nella formula o nell'aspettativa.
Le convenzioni (rendimenti aritmetici, ddof=1, downside su tutte le osservazioni)
sono quelle dichiarate in testa a metrics.py e vengono fissate qui.
"""
import math

import pandas as pd
import pytest

from metrics import daily_returns, max_drawdown, periods_per_year, risk_metrics


def serie(valori, inizio="2020-01-01", freq="B"):
    idx = pd.date_range(inizio, periods=len(valori), freq=freq)
    return pd.Series(valori, index=idx, dtype="float64")


# --- periodi per anno -----------------------------------------------------

@pytest.mark.parametrize("freq,atteso", [("B", 261), ("W", 52), ("ME", 12), ("QE", 4)])
def test_periodi_per_anno_dedotti_dalla_cadenza(freq, atteso):
    """261 e non 252 sul calendario lun-ven: senza festivi i giorni feriali sono
    5/7 di 365,25. Il dato reale (con le festivita' di borsa) scende a ~252, ed e'
    il motivo per cui il valore va dedotto dalla serie e non cablato."""
    idx = pd.date_range("2020-01-01", periods=41, freq=freq)
    assert periods_per_year(idx) == pytest.approx(atteso, rel=0.03)


def test_su_dati_reali_i_periodi_per_anno_sono_quelli_di_borsa():
    """Con le festivita' di borsa il conteggio torna a ~252."""
    import os
    percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "Timeseries.csv")
    if not os.path.exists(percorso):
        pytest.skip("Timeseries.csv assente")
    df = pd.read_csv(percorso, sep=";")
    idx = pd.to_datetime(df["Date"], dayfirst=True)
    # la serie storica parte nel 1969 con cadenza settimanale e diventa giornaliera
    # piu' avanti: la finestra va scelta, non presa dalla testa del file.
    idx = idx[idx >= pd.Timestamp("2020-01-01")]
    assert 245 <= periods_per_year(idx) <= 255


def test_periodi_per_anno_con_una_sola_data_torna_al_default():
    assert periods_per_year(pd.DatetimeIndex(["2020-01-01"])) == 252


# --- rendimenti -----------------------------------------------------------

def test_rendimenti_semplici_giornalieri():
    r = daily_returns(serie([100.0, 110.0, 99.0]))
    assert r.iloc[0] == pytest.approx(0.10)
    assert r.iloc[1] == pytest.approx(-0.10)
    assert len(r) == 2      # il primo giorno non ha rendimento


def test_rendimenti_scartano_i_valori_mancanti():
    s = serie([100.0, None, 110.0])
    r = daily_returns(s)
    assert len(r) == 0      # 110/NaN e NaN: nessun rendimento calcolabile


# --- drawdown -------------------------------------------------------------

def test_drawdown_massimo_con_picco_e_minimo_noti():
    """100 -> 120 -> 90 -> 130: picco 120, minimo 90, drawdown -25%, -30 EUR."""
    s = serie([100.0, 120.0, 90.0, 130.0])
    d = max_drawdown(s)
    assert d["max_drawdown"] == pytest.approx(-0.25)
    assert d["peak_value"] == pytest.approx(120.0)
    assert d["trough_value"] == pytest.approx(90.0)
    assert d["amount"] == pytest.approx(-30.0)
    assert d["peak_date"] == s.index[1]
    assert d["trough_date"] == s.index[2]


def test_serie_sempre_crescente_non_ha_drawdown():
    d = max_drawdown(serie([100.0, 101.0, 102.0, 103.0]))
    assert d["max_drawdown"] == pytest.approx(0.0)
    assert d["amount"] == pytest.approx(0.0)


def test_drawdown_di_una_serie_troppo_corta_e_none():
    d = max_drawdown(serie([100.0]))
    assert d["max_drawdown"] is None
    assert d["peak_date"] is None


# --- volatilita, Sharpe, Sortino -----------------------------------------

def test_volatilita_e_la_deviazione_campionaria_annualizzata():
    """Rendimenti +10% e -10%: std campionaria = 0,1414; annualizzata su 252 giorni."""
    s = serie([100.0, 110.0, 99.0])
    m = risk_metrics(s)
    rendimenti = pd.Series([0.10, -0.10])
    vol_attesa = float(rendimenti.std(ddof=1)) * math.sqrt(m["periods_per_year"])
    assert m["volatility"] == pytest.approx(vol_attesa)


def test_sharpe_usa_il_rendimento_aritmetico_annualizzato():
    """Convenzione dichiarata: numeratore = media aritmetica * periodi - risk free."""
    s = serie([100.0, 110.0, 99.0])
    m = risk_metrics(s, risk_free_rate=0.02)
    rendimenti = pd.Series([0.10, -0.10])
    atteso = (float(rendimenti.mean()) * m["periods_per_year"] - 0.02) / m["volatility"]
    assert m["sharpe"] == pytest.approx(atteso)


def test_serie_piatta_non_ha_volatilita_ne_sharpe():
    """Volatilita' zero: si restituisce None, non un rapporto infinito."""
    m = risk_metrics(serie([100.0] * 10))
    assert m["volatility"] is None
    assert m["sharpe"] is None
    assert m["sortino"] is None
    assert m["max_drawdown"] == pytest.approx(0.0)


def test_sortino_e_none_quando_non_esistono_rendimenti_negativi():
    """La downside deviation include tutte le osservazioni: senza rendimenti
    negativi il denominatore e' zero e il rapporto non e' calcolabile."""
    m = risk_metrics(serie([100.0, 101.0, 102.0, 103.0]))
    assert m["sortino"] is None


def test_sortino_esiste_e_usa_la_downside_su_tutte_le_osservazioni():
    """Rendimenti [+10%, -5%]: downside = sqrt(mean([0, 0.05^2])) * sqrt(ppy)."""
    s = serie([100.0, 110.0, 104.5])
    m = risk_metrics(s)
    ppy = m["periods_per_year"]
    downside = math.sqrt((0.0 ** 2 + 0.05 ** 2) / 2) * math.sqrt(ppy)
    atteso = (pd.Series([0.10, -0.05]).mean() * ppy) / downside
    assert m["sortino"] == pytest.approx(atteso)


def test_serie_troppo_corta_non_produce_metriche():
    m = risk_metrics(serie([100.0, 101.0]))
    assert m["observations"] == 1
    assert m["volatility"] is None
    assert m["sharpe"] is None


def test_i_nan_vengono_scartati_prima_del_calcolo():
    s = serie([100.0, 110.0, 99.0, 121.0])
    s.iloc[1] = float("nan")
    m = risk_metrics(s)
    assert m["observations"] == 2      # 99->121 e il salto su NaN non conta

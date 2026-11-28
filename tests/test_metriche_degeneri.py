"""Metriche di rischio sui casi degeneri: dove il numero non esiste.

Il motore dichiara (docstring di `metrics.py`) che un valore non calcolabile
restituisce `None` invece di un numero inventato. Qui si verifica quella promessa,
perche' un `inf` o un `NaN` che sfugge non fa fallire niente: entra in una tabella,
in un confronto, e produce una conclusione sbagliata senza errore.

Nessuna di queste funzioni aveva un caso limite fissato da un test.
"""
import math

import pandas as pd
import pytest

from metrics import (daily_returns, max_drawdown, periods_per_year,
                     risk_metrics, ulcer_index)

INDICE_GIORNALIERO = pd.bdate_range("2020-01-01", periods=253)


def serie(valori, indice=None):
    indice = indice if indice is not None else INDICE_GIORNALIERO[:len(valori)]
    return pd.Series(valori, index=indice, dtype="float64")


# --------------------------------------------------------------- serie costante

def test_serie_costante_non_inventa_sharpe():
    """Con volatilita' zero non esiste Sharpe: deve essere None, non inf ne' 0.

    Un `inf` a denominatore zero e' il modo classico in cui un rapporto senza senso
    finisce in una tabella e sembra il migliore della lista.
    """
    m = risk_metrics(serie([100.0] * 50))
    assert m["volatility"] is None
    assert m["sharpe"] is None
    assert m["sortino"] is None
    assert m["max_drawdown"] == pytest.approx(0.0)
    assert m["ulcer_index"] == pytest.approx(0.0)
    assert m["calmar"] is None           # senza drawdown Calmar non e' definito
    for chiave, valore in m.items():
        if isinstance(valore, float):
            assert math.isfinite(valore), f"{chiave} non finito: {valore}"


# --------------------------------------------------------------- serie crescente

def test_serie_sempre_crescente_ha_drawdown_zero_e_calmar_non_definito():
    valori = [100.0 * 1.001 ** i for i in range(200)]
    m = risk_metrics(serie(valori))
    assert m["max_drawdown"] == pytest.approx(0.0)
    assert m["peak_date"] is not None and m["trough_date"] is not None
    assert m["amount"] == pytest.approx(0.0)
    assert m["calmar"] is None
    # Serie che sale sempre: la downside deviation e' zero, quindi il Sortino non esiste
    # (e' corretto che sia None: non e' un rapporto, e' un denominatore nullo).
    assert m["sortino"] is None
    assert m["sharpe"] is not None


# ------------------------------------------------------------ rendimento -100%

def test_un_rendimento_del_meno_cento_per_cento_non_esplode():
    """Se il capitale arriva a zero, il CAGR geometrico non esiste: None, non eccezione.
    E' il caso che nella realta' significa 'portafoglio azzerato' e va mostrato come
    assenza di numero, non come errore di programma."""
    valori = [100.0, 100.0, 100.0, 0.0001]
    m = risk_metrics(serie(valori))
    assert m["max_drawdown"] == pytest.approx(-1.0 + 0.000001, abs=1e-6)
    assert m["calmar"] is None or math.isfinite(m["calmar"])
    for chiave, valore in m.items():
        if isinstance(valore, float):
            assert math.isfinite(valore), f"{chiave} non finito: {valore}"


# ------------------------------------------------------------------ identita'

def test_calmar_e_esattamente_cagr_diviso_drawdown():
    """L'identita' che lega Calmar al CAGR: se un giorno cambia, la tabella del report
    mostra due numeri che non si spiegano a vicenda."""
    valori = [100, 110, 90, 120, 100, 130, 115, 140]
    m = risk_metrics(serie(valori, pd.bdate_range("2020-01-01", periods=8)))
    rets = daily_returns(serie(valori, pd.bdate_range("2020-01-01", periods=8)))
    anni = len(rets) / m["periods_per_year"]
    cagr = float((1.0 + rets).prod()) ** (1.0 / anni) - 1.0
    assert m["calmar"] == pytest.approx(cagr / abs(m["max_drawdown"]), rel=1e-12)


def test_ulcer_non_supera_mai_il_drawdown_massimo():
    """L'Ulcer e' una media quadratica dei drawdown: non puo' essere piu' profondo del
    punto peggiore. Se lo supera, le due serie non stanno misurando la stessa cosa."""
    for valori in ([100, 120, 80, 90, 70, 130], [100, 99, 98, 97, 96],
                   [100, 101, 100, 102, 101, 103]):
        s = serie(valori, pd.bdate_range("2020-01-01", periods=len(valori)))
        assert ulcer_index(s) <= abs(max_drawdown(s)["max_drawdown"]) + 1e-12


def test_max_drawdown_di_un_caso_calcolato_a_mano():
    """Da 100 a 150 (+50%) poi a 75 (-50% dal picco): drawdown -50%, importo -75."""
    s = serie([100.0, 150.0, 75.0], pd.bdate_range("2020-01-01", periods=3))
    d = max_drawdown(s)
    assert d["max_drawdown"] == pytest.approx(-0.5)
    assert d["peak_value"] == pytest.approx(150.0)
    assert d["trough_value"] == pytest.approx(75.0)
    assert d["amount"] == pytest.approx(-75.0)
    assert d["peak_date"] < d["trough_date"]


# ------------------------------------------------------- rendimenti e periodi

def test_i_rendimenti_non_trascinano_i_buchi():
    """Nessun fill: un valore mancante toglie la riga, non viene sostituito col
    precedente (che produrrebbe un rendimento zero finto e abbasserebbe la volatilita')."""
    v = pd.Series([100.0, 110.0, None, 121.0], index=pd.bdate_range("2020-01-01", periods=4))
    r = daily_returns(v)
    assert len(r) == 1
    assert r.iloc[0] == pytest.approx(0.10)      # 110/100


def test_un_buco_nel_mezzo_costa_anche_il_rendimento_dopo():
    """COMPORTAMENTO ATTUALE, da conoscere prima di fidarsi delle serie con buchi.

    Scartare il NaN senza riempirlo toglie due rendimenti, non uno: quello che entra
    nel buco e anche quello che ne esce, perche' `shift(1)` porta avanti il NaN e non
    l'ultimo valore disponibile. Fra 110 e 121 il rendimento sarebbe calcolabile (ci
    sono entrambi i prezzi) ma viene perso.

    Non e' un errore di calcolo: e' la conseguenza dichiarata della scelta "nessun
    fill". Va solo saputa, perche' su una serie con buchi frequenti (un asset che
    parte dopo, un giorno di borsa chiusa) le osservazioni diminuiscono piu' del
    previsto e la volatilita' cambia di conseguenza.
    """
    v = pd.Series([100.0, 110.0, None, 121.0], index=pd.bdate_range("2020-01-01", periods=4))
    r = daily_returns(v)
    assert len(r) == 1, "due rendimenti persi, non uno"


@pytest.mark.parametrize("frequenza,atteso", [("B", 252), ("W", 52), ("ME", 12)])
def test_i_periodi_per_anno_seguono_la_frequenza_della_serie(frequenza, atteso):
    """Annualizzare una serie mensile con 252 gonfia tutto di 4,6x: il numero di periodi
    si deduce dalle date, non e' cablato."""
    indice = pd.date_range("2015-01-01", periods=120, freq=frequenza)
    ppy = periods_per_year(indice)
    assert abs(ppy - atteso) <= max(1, atteso * 0.05), f"{frequenza}: {ppy} invece di {atteso}"


def test_indice_non_di_date_non_fa_esplodere_i_periodi():
    """La funzione ha un tetto: un indice che non e' di date torna al default 252
    invece di propagare l'eccezione fino al report."""
    assert periods_per_year(pd.Index(["a", "b", "c"])) == 252
    assert periods_per_year(pd.Index([])) == 252
    assert periods_per_year(pd.Index([pd.Timestamp("2020-01-01")])) == 252


def test_serie_di_un_solo_punto_non_produce_metriche():
    m = risk_metrics(serie([100.0]))
    assert m["observations"] == 0
    assert m["volatility"] is None and m["sharpe"] is None
    assert m["max_drawdown"] is None
    assert m["ulcer_index"] is None

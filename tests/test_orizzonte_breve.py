"""Orizzonte breve (issue #88): l'annualizzazione non si arrotonda, e si avvisa.

Due difetti in uno, e il secondo e' quello che l'utente legge.

1. `years = round(giorni / 365.25, 2)` arrotondava l'**esponente** del CAGR: su 5 giorni
   di borsa 0,0164 diventava 0,02, e il CAGR passava da 32.996% a 11.639%. Su 25 anni
   l'errore era di 0,008 pt — invisibile, ma era un errore.
2. Sotto i dieci anni il numero e' poco informativo: dipende quasi solo dai due estremi.
   La simulazione non va impedita (un periodo breve si puo' volere lo stesso), ma va
   dichiarata — nel motore, nel riepilogo e nell'interfaccia.
"""
import warnings

import pandas as pd
import pytest

from backtester import (ANNI_MINIMI_AFFIDABILI, backtest,
                        messaggio_orizzonte_breve)

DATASET = __file__.rsplit("/tests/", 1)[0] + "/Timeseries.csv"


def sintetico(prezzi, inizio="2020-01-01"):
    date = pd.bdate_range(inizio, periods=len(prezzi))
    percorso = "/tmp/caso_orizzonte.csv"
    pd.DataFrame({"Date": date.strftime("%d/%m/%Y"), "A": prezzi}).to_csv(percorso, sep=";", index=False)
    return percorso, date


def esegui(percorso, **kw):
    return backtest(100_000.0, {"A": 1.0}, data_path=percorso, save_outputs=False, **kw)


# ------------------------------------------ l'annualizzazione non si arrotonda

def test_il_cagr_usa_gli_anni_non_arrotondati():
    """5 giorni di borsa, +10%: il CAGR deve usare 0,0164 anni, non 0,02."""
    percorso, date = sintetico([100.0, 100, 100, 100, 110.0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, _, s = esegui(percorso)
    anni_veri = (date[-1] - date[0]).days / 365.25
    assert s["years"] == pytest.approx(anni_veri, abs=1e-12), "gli anni non devono essere arrotondati"
    assert s["cagr_broker"] == pytest.approx(1.10 ** (1 / anni_veri) - 1, abs=1e-9)
    # il valore sbagliato che si otteneva arrotondando a 0,02
    assert s["cagr_broker"] != pytest.approx(1.10 ** (1 / 0.02) - 1, abs=1e-6)


def test_su_finestra_lunga_gli_anni_sono_ancora_esatti():
    """Su 25 anni l'arrotondamento era innocuo, ma il valore deve restare quello vero."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, _, s = backtest(100_000.0, {"VTSIM": 1.0}, begin_date="2000-01-03",
                           end_date="2025-09-04", data_path=DATASET, save_outputs=False)
    atteso = (s["end_date"] - s["begin_date"]).days / 365.25
    assert s["years"] == pytest.approx(atteso, abs=1e-12)


# ------------------------------------------------ avviso sotto la soglia

def test_avviso_su_orizzonte_breve():
    percorso, _ = sintetico([100.0 + i for i in range(760)])          # ~3 anni di borsa
    with pytest.warns(UserWarning, match="affidabil"):
        _, _, s = esegui(percorso)
    assert s["orizzonte_breve"] is True
    assert "affidabil" in s["avviso_orizzonte"]
    assert f"{s['years']:.1f}" in s["avviso_orizzonte"], "l'avviso deve dire quanto è corto"


def test_nessun_avviso_sopra_la_soglia():
    with warnings.catch_warnings(record=True) as raccolti:
        warnings.simplefilter("always")
        _, _, s = backtest(100_000.0, {"VTSIM": 1.0}, begin_date="2000-01-03",
                           end_date="2025-09-04", data_path=DATASET, save_outputs=False)
    assert [w for w in raccolti if "Orizzonte breve" in str(w.message)] == []
    assert s["orizzonte_breve"] is False
    assert s["avviso_orizzonte"] is None


def test_la_soglia_e_dichiarata_in_un_posto_solo():
    assert ANNI_MINIMI_AFFIDABILI == 10
    assert messaggio_orizzonte_breve(10.0) is None        # al limite: nessun avviso
    assert messaggio_orizzonte_breve(9.99) is not None    # appena sotto: avviso
    assert messaggio_orizzonte_breve(None) is None        # dato mancante: nessun avviso
    assert messaggio_orizzonte_breve(1.0) is not None


def test_un_orizzonte_breve_non_viene_impedito():
    """Il warning non deve diventare un divieto: la simulazione si esegue."""
    percorso, _ = sintetico([100.0 + i for i in range(400)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        log, delta, s = esegui(percorso)
    assert len(log) == 400
    assert s["final_broker"] > 0
    assert s["cagr_broker"] is not None


# ------------------------------------------------------- interfaccia

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest
APP = __file__.rsplit("/tests/", 1)[0] + "/streamlit_app.py"


def avvia():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    return at


def bottone(at, etichetta):
    return next(b for b in at.button if b.label == etichetta)


def avvisi(at):
    return " | ".join(w.value for w in at.warning)


@pytest.mark.ui
def test_interfaccia_avvisa_su_dates_brevi_e_lascia_eseguire():
    """Date a mano su 3 anni: avviso visibile prima del clic, e il backtest parte."""
    at = avvia()
    at.checkbox[0].set_value(False).run()                      # orizzonte automatico spento
    at.date_input[0].set_value(pd.Timestamp("2022-01-03").date()).run()
    at.date_input[1].set_value(pd.Timestamp("2025-09-01").date()).run()
    assert "affidabil" in avvisi(at), f"avvisi presenti: {avvisi(at)!r}"
    bottone(at, "Esegui backtest").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any(c.value.startswith("Simulato dal") for c in at.caption), "la simulazione deve girare"


@pytest.mark.ui
def test_interfaccia_non_avvisa_su_orizzonte_lungo():
    at = avvia()
    at.checkbox[0].set_value(True).run()                       # finestra automatica: 25 anni
    assert "affidabil" not in avvisi(at), f"avvisi presenti: {avvisi(at)!r}"

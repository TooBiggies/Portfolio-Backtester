"""Test dell'interfaccia Streamlit con AppTest (headless, senza browser).

Girano solo dove streamlit e' installato: la suite veloce del motore non lo richiede.
In CI c'e' un job dedicato che installa streamlit e lancia `pytest -m ui`.

I selettori sono per **chiave** e per **etichetta del bottone**, non per indice: le PR
#60 (portafogli predefiniti, descrizioni negli asset) e #59 (quota titoli di Stato)
aggiungono widget alla stessa pagina, e un indice cablato smette di puntare a quello
che si crede non appena arrivano.

Cosa NON coprono: l'aspetto grafico e il rendering reale. Coprono il comportamento:
quali campi esistono, cosa succede quando i pesi non sommano a 100, che le metriche
compaiano con i numeri giusti e che il download sia disponibile.
"""
from pathlib import Path

import pytest

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest

APP = Path(__file__).resolve().parent.parent / "streamlit_app.py"
pytestmark = pytest.mark.ui

ASSET = ["VTSIM", "GLDSIM", "ZROZSIM", "DBMFSIM"]


def avvia():
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    return at


def campo_peso(at, asset):
    """Il campo si prende per chiave: l'etichetta cambia se si aggiungono descrizioni."""
    return next(x for x in at.number_input if x.key == f"w_{asset}")


def campo_per_etichetta(at, testo):
    return next(x for x in at.number_input if testo in x.label)


def bottone(at, etichetta):
    """Per etichetta, non per indice: la pagina puo' avere altri bottoni (i preset)."""
    return next(b for b in at.button if b.label == etichetta)


def metrica(at, etichetta):
    return next(x.value for x in at.metric if x.label == etichetta)


def esegui_backtest(at):
    bottone(at, "Esegui backtest").click()
    at.run()


def test_l_app_parte_senza_eccezioni():
    at = avvia()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "Portfolio Backtester"


def test_ci_sono_i_campi_di_peso_per_ogni_asset():
    at = avvia()
    chiavi = {x.key for x in at.number_input if x.key and x.key.startswith("w_")}
    assert {f"w_{a}" for a in ASSET}.issubset(chiavi)
    for asset in ASSET:
        assert campo_peso(at, asset) is not None


def test_l_allocazione_di_default_somma_a_cento():
    at = avvia()
    assert metrica(at, "Totale allocazione") == "100.00%"


def test_cambiare_un_peso_aggiorna_il_totale():
    at = avvia()
    campo_peso(at, "VTSIM").set_value(50.0)
    at.run()
    assert metrica(at, "Totale allocazione") == "90.00%"


def test_pesi_che_non_sommano_a_cento_bloccano_il_backtest():
    at = avvia()
    campo_peso(at, "VTSIM").set_value(50.0)
    at.run()
    esegui_backtest(at)
    assert at.error, "doveva comparire un errore"
    assert "100" in at.error[0].value
    assert not [m for m in at.metric if m.label.startswith("Valore finale")]


def test_data_iniziale_dopo_la_finale_mostra_errore():
    import datetime as dt
    at = avvia()
    at.date_input[0].set_value(dt.date(2021, 1, 1))
    at.date_input[1].set_value(dt.date(2020, 1, 1))
    at.run()
    esegui_backtest(at)
    assert at.error and "precedere" in at.error[0].value


def test_backtest_valido_mostra_valori_finali_metriche_e_download():
    import datetime as dt
    at = avvia()
    at.date_input[0].set_value(dt.date(2020, 1, 2))
    at.date_input[1].set_value(dt.date(2020, 3, 2))
    at.run()
    esegui_backtest(at)
    assert not at.exception
    assert not at.error
    for etichetta in ("Valore finale lordo", "Valore finale broker", "Valore finale netto"):
        assert metrica(at, etichetta).startswith("€")
    for etichetta in ("Volatilità annua", "Max drawdown", "Sharpe / Sortino"):
        assert etichetta in [m.label for m in at.metric]
    assert at.get("download_button"), "manca il download dei risultati"


def test_l_aliquota_cambia_il_valore_netto_ma_non_il_lordo():
    """La verifica che l'aliquota inserita in interfaccia arrivi davvero al motore."""
    import datetime as dt

    def run_con(aliquota):
        at = avvia()
        campo_per_etichetta(at, "Aliquota fiscale").set_value(aliquota)
        at.date_input[0].set_value(dt.date(2020, 1, 2))
        at.date_input[1].set_value(dt.date(2020, 6, 1))
        at.run()
        esegui_backtest(at)
        return metrica(at, "Valore finale lordo"), metrica(at, "Valore finale netto")

    lordo_0, netto_0 = run_con(0.0)
    lordo_26, netto_26 = run_con(26.0)
    assert lordo_0 == lordo_26, "il lordo non deve dipendere dall'aliquota"
    assert netto_0 != netto_26, "il netto deve dipendere dall'aliquota"

"""Test dell'interfaccia Streamlit con AppTest (headless, senza browser).

Girano solo dove streamlit e' installato: la suite veloce del motore non lo richiede.
In CI c'e' un job dedicato che installa streamlit==1.54.0 (quello pinnato in
requirements.txt) e lancia `pytest -m ui`.

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


def campo(at, etichetta):
    return next(x for x in at.number_input if x.label == etichetta)


def metrica(at, etichetta):
    return next(x.value for x in at.metric if x.label == etichetta)


def test_l_app_parte_senza_eccezioni():
    at = avvia()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "Portfolio Backtester"


def test_ci_sono_i_campi_di_peso_per_ogni_asset():
    at = avvia()
    with_key = {x.key for x in at.number_input if x.key and x.key.startswith("w_")}
    assert set(ASSET).issubset({k[2:] for k in with_key})
    for asset in ASSET:
        assert campo(at, f"{asset} (%)") is not None


def test_l_allocazione_di_default_somma_a_cento():
    at = avvia()
    assert metrica(at, "Totale allocazione") == "100.00%"


def test_cambiare_un_peso_aggiorna_il_totale():
    at = avvia()
    campi = {x.key: x for x in at.number_input if x.key and x.key.startswith("w_")}
    campi["w_VTSIM"].set_value(50.0)
    at.run()
    assert metrica(at, "Totale allocazione") == "90.00%"


def test_pesi_che_non_sommano_a_cento_bloccano_il_backtest():
    at = avvia()
    campi = {x.key: x for x in at.number_input if x.key and x.key.startswith("w_")}
    campi["w_VTSIM"].set_value(50.0)
    at.run()
    at.button[0].click()
    at.run()
    assert at.error, "doveva comparire un errore"
    assert "100" in at.error[0].value
    assert not [m for m in at.metric if m.label.startswith("Valore finale")]


def test_data_iniziale_dopo_la_finale_mostra_errore():
    at = avvia()
    import datetime as dt
    data = [x for x in at.date_input]
    data[0].set_value(dt.date(2021, 1, 1))
    data[1].set_value(dt.date(2020, 1, 1))
    at.run()
    at.button[0].click()
    at.run()
    assert at.error and "precedere" in at.error[0].value


def test_backtest_valido_mostra_valori_finali_metriche_e_download():
    import datetime as dt
    at = avvia()
    data = [x for x in at.date_input]
    data[0].set_value(dt.date(2020, 1, 2))
    data[1].set_value(dt.date(2020, 3, 2))
    at.run()
    at.button[0].click()
    at.run()
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

    def esegui(aliquota):
        at = avvia()
        campo(at, "Aliquota fiscale (%)").set_value(aliquota)
        data = [x for x in at.date_input]
        data[0].set_value(dt.date(2020, 1, 2))
        data[1].set_value(dt.date(2020, 6, 1))
        at.run()
        at.button[0].click()
        at.run()
        return metrica(at, "Valore finale lordo"), metrica(at, "Valore finale netto")

    lordo_0, netto_0 = esegui(0.0)
    lordo_26, netto_26 = esegui(26.0)
    assert lordo_0 == lordo_26, "il lordo non deve dipendere dall'aliquota"
    assert netto_0 != netto_26, "il netto deve dipendere dall'aliquota"

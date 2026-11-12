"""Orizzonte temporale automatico (issue #8).

AC1: con le date vuote, la data iniziale deve essere la meno recente fra quelle comuni a
tutti gli strumenti in portafoglio. Il motore lo fa già da prima di questa modifica
(`prepare_price_dataframe` calcola l'intersezione quando `begin_date`/`end_date` sono
`None`); quello che mancava era **il modo di chiederlo dall'interfaccia**, dove i due
`date_input` hanno sempre un valore e quindi "date vuote" non esisteva.

Questi test verificano il percorso completo: attivando "Orizzonte automatico" il motore deve
ricevere `None` e la finestra mostrata deve essere quella comune, non quella di default.
"""
import datetime as dt

import pytest

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest

APP = __file__.rsplit("/tests/", 1)[0] + "/streamlit_app.py"
pytestmark = pytest.mark.ui


def avvia():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    return at


def bottone(at, etichetta):
    return next(b for b in at.button if b.label == etichetta)


def caption_unite(at):
    return " | ".join(c.value for c in at.caption)


def data_usata(at):
    """Legge dal riquadro 'Simulato dal ... al ...' la finestra effettiva del motore."""
    for testo in (c.value for c in at.caption):
        if testo.startswith("Simulato dal"):
            cifre = "".join(c if c.isdigit() or c == "-" else " " for c in testo).split()
            return dt.date.fromisoformat(cifre[0]), dt.date.fromisoformat(cifre[1])
    raise AssertionError("la finestra usata non è dichiarata nell'interfaccia")


def test_con_orizzonte_automatico_i_campi_data_spariscono():
    at = avvia()
    assert len(at.date_input) == 2, "di default ci sono i due campi data"
    at.checkbox[0].set_value(True).run()
    assert len(at.date_input) == 0, "con l'orizzonte automatico non ci sono date da compilare"


def test_orizzonte_automatico_usa_la_finestra_comune_a_tutti_gli_strumenti():
    """Con il portafoglio di default (60/10/20/10) lo strumento che parte più tardi è
    DBMFSIM, il 3 gennaio 2000: la simulazione deve partire da lì, non dal 2001 del campo
    data né dal 1969 di VTSIM."""
    at = avvia()
    at.checkbox[0].set_value(True).run()
    bottone(at, "Esegui backtest").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    inizio, fine = data_usata(at)
    assert inizio == dt.date(2000, 1, 3), inizio
    assert fine > dt.date(2025, 1, 1), fine


def test_la_finestra_comune_dipende_dagli_strumenti_scelti():
    """Con il solo azionario globale la storia comune arriva al 1969: la finestra automatica
    non è una costante dell'applicazione, è una proprietà del portafoglio."""
    at = avvia()
    at.selectbox[0].set_value("Solo azionario globale").run()
    bottone(at, "Carica il portafoglio predefinito").click().run()
    at.checkbox[0].set_value(True).run()
    bottone(at, "Esegui backtest").click().run()
    inizio, _ = data_usata(at)
    assert inizio.year <= 1970, inizio


def test_l_orizzonte_automatico_e_dichiarato_prima_di_lanciare():
    """L'utente deve sapere quale finestra verrà usata senza dover lanciare il backtest,
    e chi la decide."""
    at = avvia()
    at.checkbox[0].set_value(True).run()
    testo = caption_unite(at)
    assert "Orizzonte automatico" in testo
    assert "2000-01-03" in testo, testo
    assert "DBMFSIM" in testo, testo


def test_senza_orizzonte_automatico_le_date_scelte_vengono_usate():
    at = avvia()
    at.date_input[0].set_value(dt.date(2020, 1, 2))
    at.date_input[1].set_value(dt.date(2021, 1, 4))
    at.run()
    bottone(at, "Esegui backtest").click().run()
    inizio, fine = data_usata(at)
    assert inizio == dt.date(2020, 1, 2) and fine == dt.date(2021, 1, 4)


def test_la_finestra_usata_e_dichiarata_anche_senza_orizzonte_automatico():
    """Il riquadro con la finestra effettiva serve sempre: con le date a mano conferma che
    il motore ha usato quelle, non le sue."""
    at = avvia()
    bottone(at, "Esegui backtest").click().run()
    inizio, fine = data_usata(at)
    assert inizio < fine
    assert inizio.year == 2001  # il valore di default del campo "Data iniziale"

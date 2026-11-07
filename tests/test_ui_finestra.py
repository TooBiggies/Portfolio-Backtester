"""L'interfaccia spiega e rimedia quando le date escono dai dati (issue #90).

Il calendario di Streamlit non si può allargare: mostra dieci anni attorno al valore
scelto. Qui si verificano le tre cose che l'app fa al posto di cambiare widget:

1. il `?` su entrambi i campi dice come scrivere l'anno;
2. se le date escono dalla finestra coperta dagli strumenti attivi, compare un messaggio
   che nomina lo strumento che la limita;
3. sotto il messaggio c'è un bottone che riporta inizio e fine dentro quella finestra,
   e dopo il clic il backtest parte.
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


def restringi(at):
    return [b for b in at.button if b.label.startswith("Restringi al")]


def errori(at):
    return " | ".join(e.value for e in at.error)


def test_entrambi_i_campi_data_spiegano_il_limite_del_calendario():
    at = avvia()
    aiuti = [d.proto.help for d in at.date_input]
    assert len(aiuti) == 2
    for aiuto in aiuti:
        assert "dieci anni" in aiuto, aiuto
        assert "scrivi l'anno" in aiuto, aiuto


def test_date_valide_non_mostrano_ne_errori_ne_bottoni():
    at = avvia()
    assert restringi(at) == []
    assert errori(at) == ""


def test_data_iniziale_fuori_finestra_mostra_il_rimedio():
    at = avvia()
    at.date_input[0].set_value(dt.date(1969, 12, 31)).run()
    assert "ha dati dal" in errori(at), errori(at)
    assert "data iniziale" in errori(at)
    bottoni = restringi(at)
    assert len(bottoni) == 1
    assert "2000-01-03" in bottoni[0].label


def test_data_finale_fuori_finestra_mostra_il_rimedio():
    at = avvia()
    at.date_input[1].set_value(dt.date(2026, 1, 15)).run()
    assert "data finale" in errori(at), errori(at)
    assert len(restringi(at)) == 1


def test_il_bottone_riporta_le_date_dentro_e_il_backtest_parte():
    at = avvia()
    at.date_input[0].set_value(dt.date(1969, 12, 31)).run()
    at.date_input[1].set_value(dt.date(2026, 1, 15)).run()
    assert len(restringi(at)) == 1
    restringi(at)[0].click().run()
    # dopo il clic: date dentro la finestra, nessun errore, nessun bottone
    assert at.date_input[0].value == dt.date(2000, 1, 3)
    assert at.date_input[1].value == dt.date(2025, 9, 4)
    assert errori(at) == ""
    assert restringi(at) == []
    # e il backtest parte davvero
    bottone(at, "Esegui backtest").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any(c.value.startswith("Simulato dal") for c in at.caption)


def test_la_finestra_segue_gli_strumenti_attivi():
    """Togliendo il managed futures (che parte nel 2000) l'inizio utile va al 1969."""
    at = avvia()
    at.selectbox[0].set_value("Solo azionario globale").run()
    bottone(at, "Carica il portafoglio predefinito").click().run()
    at.date_input[0].set_value(dt.date(1969, 12, 31)).run()
    # con il solo azionario globale il 1969 è coperto: nessun errore
    assert errori(at) == ""
    assert restringi(at) == []

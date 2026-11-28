"""La scala logaritmica è una vista, non un nuovo calcolo.

Il rischio vero non è il grafico: è che cambiare una vista faccia ripartire lo script con
il bottone non premuto e cancelli la tabella appena calcolata. Questo test sorveglia
entrambe le cose.
"""
from pathlib import Path

import pytest

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest

from conftest import imposta_allocazione, imposta_orizzonte_automatico

APP = Path(__file__).resolve().parent.parent / "streamlit_app.py"
pytestmark = [pytest.mark.ui, pytest.mark.dati]


def esegui_breve():
    """Backtest su un anno: veloce, e sufficiente a produrre le tre curve."""
    import datetime as dt

    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    imposta_allocazione(at, {"VTSIM": 60.0, "GLDSIM": 10.0, "ZROZSIM": 25.0, "DBMFSIM": 5.0})
    imposta_orizzonte_automatico(at, False)
    at.date_input[0].set_value(dt.date(2020, 1, 2)).run()
    at.date_input[1].set_value(dt.date(2021, 1, 2)).run()
    next(b for b in at.button if b.label == "Esegui backtest").click().run()
    return at


def test_il_grafico_ha_l_opzione_logaritmica():
    at = esegui_breve()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any(c.key == "scala_log" for c in at.checkbox)


def test_cambiare_scala_non_cancella_i_risultati():
    """Attivando la scala logaritmica la tabella resta: i risultati vivono in sessione."""
    at = esegui_breve()
    schede_prima = len(at.get("download_button"))
    next(c for c in at.checkbox if c.key == "scala_log").set_value(True).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.get("download_button")) == schede_prima == 1
    next(c for c in at.checkbox if c.key == "scala_log").set_value(False).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert len(at.get("download_button")) == 1

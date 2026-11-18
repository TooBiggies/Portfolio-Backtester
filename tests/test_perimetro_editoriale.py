"""Perimetro editoriale dell'app: cosa dichiara, e cosa non deve più esserci.

Il vincolo non è tecnico: uno strumento pubblico che propone allocazioni con un nome
proprio («Classico 60/40», «All weather»…) è, per un'autorità di vigilanza, un portafoglio
modello — cioè una raccomandazione a un pubblico indistinto. Questi test tengono ferma la
scelta: se qualcuno reintroduce un portafoglio predefinito, la suite lo dice subito.
"""
from pathlib import Path

import pandas as pd
import pytest

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest

RADICE = Path(__file__).resolve().parent.parent
APP = str(RADICE / "streamlit_app.py")
sorgente = (RADICE / "streamlit_app.py").read_text(encoding="utf-8")
# I nomi possono comparire nei commenti — dove servono a spiegare perché sono stati
# rimossi — ma non nel codice: qui si guardano solo le righe che non sono commento.
codice = "\n".join(riga for riga in sorgente.splitlines()
                   if not riga.lstrip().startswith("#"))

pytestmark = pytest.mark.ui


def avvia():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    return at


def estrai_testi(at):
    """Tutto il testo che l'utente legge, senza dipendere dal tipo di elemento."""
    pezzi = []
    for attributo in ("markdown", "caption", "info", "warning", "error"):
        elementi = getattr(at, attributo, None)
        if elementi:
            pezzi.extend(str(getattr(e, "value", "")) for e in elementi)
    return " ".join(pezzi)


def test_la_pagina_dichiara_che_e_uno_strumento_didattico():
    at = avvia()
    assert not at.exception, [str(e.value) for e in at.exception]
    testo = estrai_testi(at).lower()
    assert "strumento didattico" in testo
    assert "non è consulenza" in testo
    assert "non contiene raccomandazioni" in testo


def test_la_pagina_dichiara_i_limiti_del_calcolo():
    at = avvia()
    testo = estrai_testi(at).lower()
    assert "minusvalenze non sono compensate" in testo
    assert "dollari" in testo


def test_la_tabella_parte_da_zero():
    """Nessun peso precompilato: l'allocazione la scrive chi usa lo strumento."""
    at = avvia()
    totale = next(m for m in at.metric if "Totale allocazione" in m.label)
    assert totale.value == "0%"


def test_nessun_portafoglio_modello_nel_codice():
    """I nomi dei sei portafogli predefiniti non devono tornare nel sorgente."""
    vietati = ["Classico 60/40", "Permanent Portfolio", "All weather",
               "Golden butterfly", "Solo azionario globale", "Portafoglio predefinito"]
    trovati = [nome for nome in vietati if nome in codice]
    assert not trovati, f"portafogli modello ancora presenti nell'app: {trovati}"


def test_senza_allocazione_il_backtest_non_parte():
    at = avvia()
    next(b for b in at.button if b.label == "Esegui backtest").click().run()
    assert any("Nessuno strumento con allocazione maggiore di zero" in w.value for w in at.warning)


def test_azzera_riporta_le_allocazioni_a_zero():
    """Il bottone di azzeramento non deve toccare costi e aliquote già impostati."""
    at = avvia()
    at.session_state["tabella_per_asset"] = pd.DataFrame(
        {
            "Allocazione (%)": [50.0, 50.0] + [0.0] * (len(at.session_state["tabella_per_asset"]) - 2),
            "Commissione (%)": [0.5] * len(at.session_state["tabella_per_asset"]),
            "Costi annui (%)": [0.3] * len(at.session_state["tabella_per_asset"]),
            "Aliquota (%)": [26.0] * len(at.session_state["tabella_per_asset"]),
        },
        index=at.session_state["tabella_per_asset"].index,
    )
    next(b for b in at.button if b.label == "Azzera le allocazioni").click().run()
    tabella = at.session_state["tabella_per_asset"]
    assert float(tabella["Allocazione (%)"].sum()) == 0.0
    assert float(tabella["Commissione (%)"].sum()) > 0.0

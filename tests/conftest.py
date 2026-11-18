"""Configurazione comune dei test.

`MPLBACKEND=Agg` va impostato prima che matplotlib venga importato: senza, su una
macchina con display matplotlib sceglie TkAgg e la creazione di una figura dentro il
thread di Streamlit (AppTest, Streamlit in generale) termina il processo con
"Fatal Python error: Illegal instruction". Un backend non interattivo rende i test
deterministici anche su un runner headless.
"""
import os

os.environ.setdefault("MPLBACKEND", "Agg")


def imposta_allocazione(at, pesi):
    """Scrive un'allocazione nella tabella di un'app AppTest.

    La tabella parte da zero — l'app non propone pesi, per una scelta editoriale
    (vedi `tests/test_perimetro_editoriale.py`) — quindi i test che devono far girare
    il motore dichiarano la propria allocazione. Il meccanismo è lo stesso del bottone
    «Azzera»: si riscrive il DataFrame in session_state e si incrementa la versione
    della tabella, che è l'unico modo per ricreare il widget `data_editor`.
    """
    tabella = at.session_state["tabella_per_asset"].copy()
    tabella["Allocazione (%)"] = [float(pesi.get(asset, 0.0)) for asset in tabella.index]
    at.session_state["tabella_per_asset"] = tabella
    at.session_state["versione_tabella"] = at.session_state.get("versione_tabella", 0) + 1
    at.run()
    return at

"""Portafogli predefiniti: devono caricare al primo clic e arrivare al motore.

Il difetto che questa suite chiude (issue #83) era di una riga e invisibile ai test:
`carica_preset(nome)` era stata riscritta con un solo argomento nel #77, mentre il
bottone continuava a passarne due (`args=(scelta_preset, assets)`). Al clic Streamlit
sollevava `TypeError: carica_preset() takes 1 positional argument but 2 were given`
e la tabella non cambiava. Nessun test premeva quel bottone, quindi la suite era verde.

Qui si verifica, per ognuno dei sei preset: che la tabella si riempia, che il totale sia
100, e che il risultato del backtest eseguito SUBITO DOPO sia quello del preset e non
quello di default (cioe' che serva un solo passaggio, non due).
"""
import datetime as dt

import pandas as pd
import pytest

from backtester import backtest

modulo = pytest.importorskip("streamlit.testing.v1", reason="streamlit non installato")
AppTest = modulo.AppTest

APP = __file__.rsplit("/tests/", 1)[0] + "/streamlit_app.py"
pytestmark = pytest.mark.ui

PRESET = {
    "Attuale (60/10/25/5)": {"VTSIM": 60, "GLDSIM": 10, "ZROZSIM": 25, "DBMFSIM": 5},
    "Classico 60/40": {"VTSIM": 60, "IEFSIM": 40},
    "Permanent Portfolio": {"VTSIM": 25, "TLTSIM": 25, "GLDSIM": 25, "CASHX": 25},
    "All weather": {"VTSIM": 30, "TLTSIM": 40, "IEFSIM": 15, "GLDSIM": 15},
    "Golden butterfly": {"VTSIM": 40, "TLTSIM": 20, "SHYSIM": 20, "GLDSIM": 20},
    "Solo azionario globale": {"VTSIM": 100},
}


def avvia():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    return at


def tabella(at):
    for riquadro in at.dataframe:
        valore = riquadro.value
        if getattr(valore, "columns", None) is not None and "Allocazione (%)" in valore.columns:
            return valore
    raise AssertionError("tabella per asset non trovata")


def tabella_risultati(at):
    for riquadro in at.dataframe:
        valore = riquadro.value
        if getattr(valore, "columns", None) is not None and "Portafoglio" in valore.columns:
            return valore
    raise AssertionError("tabella dei risultati non trovata")


def bottone(at, etichetta):
    return next(b for b in at.button if b.label == etichetta)


def carica_preset(at, nome):
    at.selectbox[0].set_value(nome).run()
    bottone(at, "Carica il portafoglio predefinito").click().run()
    return at


def test_il_bottone_dei_preset_non_solleva_eccezioni():
    """La regressione esatta del #77: prima di questo fix il clic produceva un TypeError."""
    at = carica_preset(avvia(), "Attuale (60/10/25/5)")
    assert not at.exception, [str(e.value) for e in at.exception]


@pytest.mark.parametrize("nome", list(PRESET))
def test_ogni_preset_riempie_la_tabella_e_somma_a_cento(nome):
    at = carica_preset(avvia(), nome)
    assert not at.exception, [str(e.value) for e in at.exception]
    allocazione = tabella(at)["Allocazione (%)"].astype(float)
    assert float(allocazione.sum()) == pytest.approx(100.0, abs=1e-9), f"{nome}: totale {allocazione.sum()}"
    for asset, atteso in PRESET[nome].items():
        assert float(allocazione[asset]) == pytest.approx(float(atteso)), f"{nome}.{asset}"
    for asset, peso in allocazione.items():
        if asset not in PRESET[nome]:
            assert peso == 0, f"{nome}: {asset} doveva essere 0, vale {peso}"


def test_il_preset_arriva_al_motore_con_un_solo_passaggio():
    """Il punto della issue #83: «le parametrizzazioni vanno inserite due volte».
    Qui si carica il preset e si esegue subito il backtest, senza toccare altro, e il
    risultato deve essere quello del 100% azionario, non quello del mix di default."""
    at = avvia()
    at.date_input[0].set_value(dt.date(2020, 1, 2))
    at.date_input[1].set_value(dt.date(2021, 1, 4))
    at.run()
    carica_preset(at, "Solo azionario globale")
    bottone(at, "Esegui backtest").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert not at.error, [e.value for e in at.error]

    tab = tabella_risultati(at)
    netto_ui = float(
        tab[tab["Portafoglio"] == "Netto"]["Valore finale"].iloc[0]
        .replace("€", "").replace("$", "").replace(",", "").strip()   # formato: 11,035.29
    )
    # I parametri si leggono dalla tabella, non si cablano: i default dell'interfaccia
    # cambiano (0,19% -> 0,1% il 30/10) e un test che li fissa diventa rosso per una
    # scelta di prodotto, non per un difetto.
    per_asset = tabella(at)
    fee = float(per_asset.loc["VTSIM", "Commissione (%)"]) / 100.0
    costi = float(per_asset.loc["VTSIM", "Costi annui (%)"]) / 100.0
    aliquota = float(per_asset.loc["VTSIM", "Aliquota (%)"]) / 100.0
    _, _, summary = backtest(
        10000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2021-01-04"),
        brokerage_fee_rate={"VTSIM": fee}, annual_costs_rate={"VTSIM": costi},
        tax_rate={"VTSIM": aliquota}, save_outputs=False)
    assert netto_ui == pytest.approx(summary["final_net"], rel=1e-6), (
        f"la tabella dice {netto_ui}, il motore con i suoi stessi parametri {summary['final_net']:.2f}")


def test_caricare_due_preset_di_fila_lascia_il_secondo():
    """Applicare un preset non deve sommare al precedente: il secondo sostituisce."""
    at = carica_preset(avvia(), "Solo azionario globale")
    carica_preset(at, "Classico 60/40")
    allocazione = tabella(at)["Allocazione (%)"].astype(float)
    assert float(allocazione["VTSIM"]) == pytest.approx(60.0)
    assert float(allocazione["IEFSIM"]) == pytest.approx(40.0)
    assert float(allocazione.sum()) == pytest.approx(100.0)


def test_il_preset_non_tocca_i_costi_per_strumento():
    """Il preset decide i pesi, non le aliquote: i Treasury devono restare al 12,5%."""
    at = carica_preset(avvia(), "Classico 60/40")
    tab = tabella(at)
    assert float(tab.loc["IEFSIM", "Aliquota (%)"]) == pytest.approx(12.5)
    assert float(tab.loc["VTSIM", "Aliquota (%)"]) == pytest.approx(26.0)


def test_la_versione_della_tabella_avanza_a_ogni_riscrittura():
    """Meccanismo del fix: il preset chiede un editor nuovo incrementando la versione,
    perche' `st.data_editor` non accetta scritture da session_state."""
    at = avvia()
    prima = at.session_state["versione_tabella"]
    carica_preset(at, "All weather")
    dopo = at.session_state["versione_tabella"]
    assert dopo == prima + 1, (prima, dopo)

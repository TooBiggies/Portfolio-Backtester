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


COLONNE_TABELLA = [
    "Portafoglio", "CAGR", "Valore finale", "Volatilità annua", "Max drawdown",
    "Sharpe (rf=0.00%)", "Sortino", "Ulcer index", "Calmar",
]


def tabella_comparativa(at):
    """La tabella dei tre portafogli si riconosce dalla colonna 'Portafoglio':
    nella pagina c'e' anche l'anteprima del log, che non ce l'ha."""
    for riquadro in at.dataframe:
        valore = riquadro.value
        if getattr(valore, "columns", None) is not None and "Portafoglio" in valore.columns:
            return valore
    raise AssertionError("tabella comparativa non trovata nella pagina")


def esegui_con_date_breve(at):
    import datetime as dt
    at.date_input[0].set_value(dt.date(2020, 1, 2))
    at.date_input[1].set_value(dt.date(2020, 3, 2))
    at.run()
    esegui_backtest(at)


def test_backtest_valido_mostra_la_tabella_e_il_download():
    at = avvia()
    esegui_con_date_breve(at)
    assert not at.exception
    assert not at.error
    tabella = tabella_comparativa(at)
    assert list(tabella["Portafoglio"]) == ["Lordo", "Broker", "Netto"]
    assert at.get("download_button"), "manca il download dei risultati"


def test_la_tabella_ha_tutte_le_metriche_per_ogni_portafoglio():
    """Criteri di accettazione della issue #75: una tabella, tre righe (Lordo, Broker,
    Netto), e per ognuna tutte le metriche disponibili, CAGR e valore finale compresi."""
    at = avvia()
    esegui_con_date_breve(at)
    tabella = tabella_comparativa(at)
    assert list(tabella.columns) == COLONNE_TABELLA
    assert len(tabella) == 3
    for colonna in COLONNE_TABELLA[1:]:
        for valore in tabella[colonna]:
            assert valore not in ("", "n.d.", None), f"{colonna} vuota: {valore}"


def test_i_tre_portafogli_hanno_metriche_diverse_e_coerenti():
    """Il lordo non paga nulla, il netto paga costi e imposte: rendimento e valore finale
    devono degradare nell'ordine Lordo > Broker > Netto, con la stessa metodologia."""
    at = avvia()
    esegui_con_date_breve(at)
    tabella = tabella_comparativa(at)

    def numero_euro(testo):
        return float(testo.replace("€", "").replace(".", "").replace(",", ".").strip())

    def percentuale(testo):
        return float(testo.replace("%", "").replace(",", ".").strip())

    finali = [numero_euro(v) for v in tabella["Valore finale"]]
    cagr = [percentuale(v) for v in tabella["CAGR"]]
    assert finali[0] > finali[1] > finali[2], finali
    assert cagr[0] > cagr[1] > cagr[2], cagr


def test_l_aliquota_cambia_il_valore_netto_ma_non_il_lordo():
    """La verifica che l'aliquota inserita in interfaccia arrivi davvero al motore:
    stesso run con 0% e 26% -> lordo identico, netto diverso."""
    import datetime as dt

    def run_con(aliquota):
        at = avvia()
        campo_per_etichetta(at, "Aliquota fiscale").set_value(aliquota)
        at.date_input[0].set_value(dt.date(2020, 1, 2))
        at.date_input[1].set_value(dt.date(2020, 6, 1))
        at.run()
        esegui_backtest(at)
        tabella = tabella_comparativa(at)
        per_portafoglio = dict(zip(tabella["Portafoglio"], tabella["Valore finale"]))
        return per_portafoglio["Lordo"], per_portafoglio["Netto"]

    lordo_0, netto_0 = run_con(0.0)
    lordo_26, netto_26 = run_con(26.0)
    assert lordo_0 == lordo_26, "il lordo non deve dipendere dall'aliquota"
    assert netto_0 != netto_26, "il netto deve dipendere dall'aliquota"

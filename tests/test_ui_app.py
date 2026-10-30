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


def tabella_asset(at):
    """La tabella per asset si riconosce dall'indice fatto di ticker."""
    for riquadro in at.dataframe:
        valore = riquadro.value
        if getattr(valore, "columns", None) is not None and "Allocazione (%)" in valore.columns:
            return valore
    raise AssertionError("tabella per asset non trovata nella pagina")


def scrivi_cella(at, asset, colonna, valore):
    """Modifica una cella come farebbe l'utente, passando dallo stato della sessione."""
    tabella = at.session_state["tabella_per_asset"].copy()
    tabella.loc[asset, colonna] = valore
    at.session_state["tabella_per_asset"] = tabella
    at.run()


def test_l_app_parte_senza_eccezioni():
    at = avvia()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "Portfolio Backtester"


def test_la_tabella_ha_una_riga_per_ogni_asset_e_le_quattro_colonne():
    at = avvia()
    tabella = tabella_asset(at)
    assert len(tabella) == len([a for a in tabella.index]) >= 11
    assert list(tabella.columns) == ["Allocazione (%)", "Commissione (%)", "Costi annui (%)", "Aliquota (%)"]
    for asset in ASSET:
        assert asset in tabella.index


def campo_globale(at, testo):
    return next(x for x in at.number_input if testo in x.label)


def test_le_celle_per_asset_partono_dai_valori_globali():
    """AC1/AC2 come invariante, non come numero: ogni riga della tabella deve partire dal
    valore dei campi generali, tranne i Treasury che partono dal 12,5% di legge.

    Cablare 0,19% rendeva questo test inutile il giorno in cui il default è cambiato
    (commit 901c919: 0,1%): qui si verifica la relazione, che è quello che conta.
    """
    at = avvia()
    tabella = tabella_asset(at)
    commissione = float(campo_globale(at, "Costi di negoziazione").value)
    costi_annui = float(campo_globale(at, "Costi annui").value)
    aliquota = float(campo_globale(at, "Aliquota fiscale").value)

    assert float((tabella["Commissione (%)"] - commissione).abs().max()) < 1e-9
    assert float((tabella["Costi annui (%)"] - costi_annui).abs().max()) < 1e-9
    for asset in ("SHYSIM", "IEFSIM", "TLTSIM", "ZROZSIM"):
        assert abs(float(tabella.loc[asset, "Aliquota (%)"]) - 12.5) < 1e-9, asset
    for asset in ("VTSIM", "GLDSIM", "KMLMSIM", "DBMFSIM", "SPYSIM", "VXUSSIM", "CASHX"):
        assert abs(float(tabella.loc[asset, "Aliquota (%)"]) - aliquota) < 1e-9, asset


def test_l_allocazione_di_default_somma_a_cento_ed_e_intera():
    at = avvia()
    assert metrica(at, "Totale allocazione") == "100%"
    allocazione = tabella_asset(at)["Allocazione (%)"]
    assert (allocazione == allocazione.astype(int)).all(), "le allocazioni hanno decimali"


def test_cambiare_un_peso_aggiorna_il_totale():
    at = avvia()
    scrivi_cella(at, "VTSIM", "Allocazione (%)", 50.0)
    assert metrica(at, "Totale allocazione") == "90%"


def test_il_bottone_applica_i_valori_globali_a_tutti():
    """AC1: i tre campi generali riscrivono tutti gli strumenti in un colpo."""
    at = avvia()
    scrivi_cella(at, "ZROZSIM", "Commissione (%)", 0.0)      # personalizzazione
    campo_per_etichetta(at, "Costi di negoziazione").set_value(0.5)
    campo_per_etichetta(at, "Costi annui").set_value(0.3)
    campo_per_etichetta(at, "Aliquota fiscale").set_value(20.0)
    at.run()
    bottone(at, "Applica i valori globali a tutti gli strumenti").click()
    at.run()
    tabella = tabella_asset(at)
    assert float((tabella["Commissione (%)"] - 0.5).abs().max()) < 1e-9
    assert float((tabella["Costi annui (%)"] - 0.3).abs().max()) < 1e-9
    assert float((tabella["Aliquota (%)"] - 20.0).abs().max()) < 1e-9


def valore_finale(at, portafoglio):
    """Il valore finale si legge dalla tabella comparativa (#76), non piu' dalle card:
    quelle sono state sostituite, e questo test le cercava ancora."""
    for riquadro in at.dataframe:
        tabella = riquadro.value
        if getattr(tabella, "columns", None) is not None and "Portafoglio" in tabella.columns:
            riga = tabella[tabella["Portafoglio"] == portafoglio]
            return str(riga["Valore finale"].iloc[0])
    raise AssertionError("tabella comparativa non trovata")


def test_la_tabella_arriva_al_motore_come_parametri_per_asset():
    """Cambiare l'aliquota di un solo strumento deve cambiare il netto e lasciare
    intatto il lordo: e' la catena interfaccia -> motore, verificata dall'esterno."""
    import datetime as dt
    at = avvia()
    at.date_input[0].set_value(dt.date(2020, 1, 2))
    at.date_input[1].set_value(dt.date(2021, 1, 4))
    at.run()
    esegui_backtest(at)
    lordo_prima = valore_finale(at, "Lordo")
    netto_prima = valore_finale(at, "Netto")

    # Si usa VTSIM, che nel portafoglio di default ha sempre peso > 0: cambiare
    # l'aliquota di uno strumento a peso zero non puo' cambiare il risultato, e il test
    # fallirebbe per la ragione sbagliata (il default 60/10/20/10 non contiene ZROZSIM).
    scrivi_cella(at, "VTSIM", "Aliquota (%)", 0.0)           # da 26% a 0%
    esegui_backtest(at)
    assert valore_finale(at, "Lordo") == lordo_prima
    assert valore_finale(at, "Netto") != netto_prima


def test_pesi_che_non_sommano_a_cento_bloccano_il_backtest():
    at = avvia()
    scrivi_cella(at, "VTSIM", "Allocazione (%)", 40.0)
    esegui_backtest(at)
    assert at.error, "manca l'errore sul totale diverso da 100"
    assert "100" in at.error[0].value


def test_data_iniziale_dopo_la_finale_mostra_errore():
    import datetime as dt
    at = avvia()
    at.date_input[0].set_value(dt.date(2021, 1, 1))
    at.date_input[1].set_value(dt.date(2020, 1, 1))
    at.run()
    esegui_backtest(at)
    assert at.error and "precedere" in at.error[0].value


# La colonna dello Sharpe contiene il tasso privo di rischio usato, che dal #79 non è
# più zero (è il cash a 3 mesi): il nome esatto della colonna dipende dai dati, quindi
# si verifica per prefisso invece di cablare un numero che cambia col periodo.
COLONNE_TABELLA = [
    "Portafoglio", "CAGR", "Valore finale", "Volatilità annua", "Max drawdown",
    "Sharpe (rf=", "Sortino", "Ulcer index", "Calmar",
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
    colonne = list(tabella.columns)
    assert len(colonne) == len(COLONNE_TABELLA)
    for atteso, reale in zip(COLONNE_TABELLA, colonne):
        if atteso.endswith("(") or atteso == "Sharpe (rf=":
            assert reale.startswith(atteso) and reale.endswith("%)"), reale
        else:
            assert reale == atteso, (reale, atteso)
    assert len(tabella) == 3
    for colonna in list(tabella.columns)[1:]:
        for valore in tabella[colonna]:
            assert valore not in ("", "n.d.", None), f"{colonna} vuota: {valore}"


def test_i_tre_portafogli_hanno_metriche_diverse_e_coerenti():
    """Il lordo non paga nulla, il netto paga costi e imposte: rendimento e valore finale
    devono degradare nell'ordine Lordo > Broker > Netto, con la stessa metodologia."""
    at = avvia()
    esegui_con_date_breve(at)
    tabella = tabella_comparativa(at)

    def numero_euro(testo):
        """Il simbolo cambia col tempo (€ -> $, commit 3f68684): il test non deve
        dipendere da quale valuta è scritta accanto al numero."""
        ripulito = "".join(c for c in testo if c.isdigit() or c in ",.-")
        return float(ripulito.replace(",", ""))

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

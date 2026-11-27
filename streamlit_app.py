from io import BytesIO

import altair as alt
import pandas as pd
import streamlit as st

from dati_storico import percorso_dataset

from backtester import backtest, anni_simulati, messaggio_orizzonte_breve
from valuta import ETICHETTE, SIMBOLI, prima_data_valida

st.set_page_config(page_title="Backtester", page_icon="📈", layout="wide")
# Il titolo è il nome dello strumento e nient'altro: la pagina è una calcolatrice, e le
# istruzioni stanno accanto ai comandi che spiegano.
st.title("Backtester")

# Cosa sono i ticker del dataset: senza questo, "VTSIM" non dice niente a chi apre la pagina.
ASSET_INFO = {
    "VTSIM":   ("Azionario globale", "Tutti i mercati sviluppati ed emergenti in un solo ETF (MSCI ACWI)."),
    "SPYSIM":  ("Azioni USA large cap", "S&P 500: le 500 maggiori società statunitensi."),
    "VXUSSIM": ("Azioni fuori dagli USA", "Mercati sviluppati ed emergenti esclusi gli Stati Uniti."),
    "GLDSIM":  ("Oro fisico", "ETC garantito da lingotti: segue il prezzo spot dell'oro, non è un OICR."),
    "CASHX":   ("Liquidità", "Contanti remunerati: quasi zero volatilità, rende poco."),
    "SHYSIM":  ("Treasury USA 1-3 anni", "Obbligazioni sovrane USA a brevissimo termine, poca duration, poca oscillazione."),
    "IEFSIM":  ("Treasury USA 7-10 anni", "Sovrano USA a media scadenza: duration ~7."),
    "TLTSIM":  ("Treasury USA 20+ anni", "Sovrano USA oltre 20 anni: molta duration, amplifica i movimenti dei tassi."),
    "ZROZSIM": ("Treasury USA 25+ zero coupon", "Zero coupon a lunghissima scadenza: la duration più alta disponibile."),
    "KMLMSIM": ("Managed futures", "Strategia trend following su futures (azioni, tassi, valute, materie prime): decorrelata."),
    "DBMFSIM": ("Managed futures replicato", "Replica della performance media dei gestori CTA (indice SG CTA)."),
}

# Portafogli predefiniti: rimossi. Erano sei costruzioni con un nome proprio («Classico
# 60/40», «All weather», «Golden butterfly»…): agli occhi di un'autorità di vigilanza sono
# portafogli modello, cioè la raccomandazione di un'allocazione a un pubblico indistinto.
# Lo strumento resta un calcolatore: l'allocazione la scrive chi lo usa, e la tabella parte
# da zero proprio perché non c'è nulla da suggerire.


# Aliquote di partenza per strumento: 12,5% sui titoli di Stato white list (base ridotta al
# 48,08%: 0,4808 x 26% = 12,5%), 26% su tutto il resto. E' un DEFAULT modificabile in tabella,
# non una regola cablata nel motore: quello che l'utente vede e' quello che viene applicato.
STRUMENTI_SOVRANI = {"SHYSIM", "IEFSIM", "TLTSIM", "ZROZSIM"}
ALIQUOTA_SOVRANA = 12.5

CHIAVE_TABELLA = "tabella_per_asset"
# Versione della tabella: cambiarla crea un editor nuovo, che riparte dai dati passati.
# E' l'unico modo di aggiornare un data_editor via codice, perche' il widget non accetta
# scritture da session_state.
def nuova_versione_tabella():
    st.session_state["versione_tabella"] = st.session_state.get("versione_tabella", 0) + 1


def azzera_allocazione():
    """Riporta a zero le allocazioni: la tabella è dell'utente, l'app non propone pesi."""
    if CHIAVE_TABELLA not in st.session_state:
        return
    tabella = st.session_state[CHIAVE_TABELLA].copy()
    tabella["Allocazione (%)"] = 0.0
    st.session_state[CHIAVE_TABELLA] = tabella
    nuova_versione_tabella()


def applica_colonna(colonna, chiave_campo):
    """Il campo generale riscrive la propria colonna su tutti gli strumenti (AC1).

    Un callback per colonna, non uno per tutti e tre: cambiare la commissione non deve
    azzerare l'aliquota che l'utente ha appena impostato a mano su un singolo strumento.
    """
    def _callback():
        tabella = st.session_state.get(CHIAVE_TABELLA)
        if tabella is None:
            return
        tabella = tabella.copy()
        tabella[colonna] = float(st.session_state[chiave_campo])
        st.session_state[CHIAVE_TABELLA] = tabella
        nuova_versione_tabella()
    return _callback


def applica_valori_globali():
    """Porta i tre campi generali su tutti gli strumenti (AC1: modifica massiva)."""
    if CHIAVE_TABELLA not in st.session_state:
        return
    tabella = st.session_state[CHIAVE_TABELLA].copy()
    tabella["Commissione (%)"] = float(st.session_state["glob_comm"])
    tabella["Costi annui (%)"] = float(st.session_state["glob_costi"])
    tabella["Aliquota (%)"] = float(st.session_state["glob_aliquota"])
    st.session_state[CHIAVE_TABELLA] = tabella
    nuova_versione_tabella()


# Il dataset non sta nel repository (vedi PERMISSION.md): il modulo sa dove cercarlo e,
# se manca, lo scarica dal deposito privato usando il token nei secret dell'app.
try:
    DATA_FILE = percorso_dataset()
except RuntimeError as _errore_dati:
    st.error(str(_errore_dati))
    st.stop()


@st.cache_data(show_spinner=False)
def carica_storico(percorso: str, versione: float) -> pd.DataFrame:
    """CSV dei prezzi, letto una volta per file.

    `versione` è la data di modifica del file: se cambia, la cache si invalida. Serve
    perché Streamlit riesegue lo script dall'inizio a ogni interazione, e senza cache
    ogni clic di ogni visitatore rileggeva 1,4 MB di serie. In locale non si nota; con
    più persone sulla stessa istanza sì.
    """
    dati = pd.read_csv(percorso, sep=";")
    dati["Date"] = pd.to_datetime(dati["Date"], dayfirst=True, errors="coerce")
    return dati.dropna(subset=["Date"])


raw = carica_storico(str(DATA_FILE), DATA_FILE.stat().st_mtime)
assets = [c for c in raw.columns if c != "Date"]
min_date = raw["Date"].min().date()
max_date = raw["Date"].max().date()
# Le serie di cambio cominciano nel 1971, il dataset dei prezzi nel 1969: chi sceglie euro
# o lire non può partire prima, e l'interfaccia non deve offrirglielo.
_min_valuta = prima_data_valida().date()


def _minimo_ammesso(valuta_scelta):
    return _min_valuta if valuta_scelta != "USD" else min_date

def finestra_comune(attivi):
    """Finestra in cui TUTTI gli strumenti attivi hanno un prezzo: (inizio, fine, chi_decide).

    È la stessa regola che applica il motore con le date vuote (issue #8); qui serve solo
    per dirlo all'utente PRIMA di lanciare, invece di farlo scoprire dopo.
    """
    partenze, fini = {}, {}
    for asset in attivi:
        serie = raw[["Date", asset]].dropna()
        serie = serie[pd.to_numeric(serie[asset], errors="coerce").notna()]
        if len(serie):
            partenze[asset] = serie["Date"].min()
            fini[asset] = serie["Date"].max()
    if not partenze:
        return None
    inizio = max(partenze.values())
    fine = min(fini.values())
    chi = next(a for a, d in partenze.items() if d == inizio)
    return inizio, fine, chi


def to_excel_bytes(df_log, df_delta):
    """Excel dei risultati, senza le serie di prezzo.

    L'export serve a mostrare la storia del portafoglio — valori, ribilanciamenti,
    imposte — non a ridistribuire i dati di mercato. Le colonne `Price_*` e `PMC_*`
    restano nel log interno (servono all'interfaccia e alle verifiche), ma non escono
    dal file scaricabile: sono anche la parte che pesa, perché sono una colonna per
    ogni giorno di borsa per ogni asset.
    """
    colonne = [c for c in df_log.columns if not c.startswith(("Price_", "PMC_"))]
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_log[colonne].to_excel(writer, sheet_name="Portfolio")
        df_delta.to_excel(writer, sheet_name="Rebalancing")
    return buffer.getvalue()


@st.cache_data(show_spinner=False, max_entries=2)
def esegui_backtest(initial_value, weights, begin_date, end_date, commissioni, costi_annui,
                    aliquote, soglia_ribilanciamento, soglia_ribilanciamento_relativa=None,
                    valuta="USD", reale=False):
    """Il backtest, memorizzato per combinazione di parametri.

    È la parte lenta (12-40 secondi su venticinque anni). Senza cache due visitatori con
    gli stessi input pagavano due volte la stessa simulazione, su un'istanza che ha un
    core solo. `max_entries=2` perché ogni voce contiene il log giornaliero per asset:
    tenerne quattro in memoria non serve e su Streamlit Community Cloud (1 GB) pesa.
    """
    return backtest(
        initial_value=initial_value,
        weights=weights,
        begin_date=begin_date,
        end_date=end_date,
        brokerage_fee_rate=commissioni,
        rebalance_threshold=soglia_ribilanciamento,
        rel_rebalance_threshold=soglia_ribilanciamento_relativa,
        tax_rate=aliquote,
        annual_costs_rate=costi_annui,
        # Sharpe e Sortino con il cash a 3 mesi come tasso privo di rischio
        # (issue #79). Con rf=0 il rapporto era sovrastimato: nel periodo
        # 2010-2025 il cash ha reso in media 1,33% l'anno.
        risk_free_rate="CASHX",
        plot=False,
        save_outputs=False,
        # La valuta e la deflazione cambiano i prezzi, non il risultato: la cache le
        # tratta come parametri, quindi ogni combinazione ha la sua voce giusta.
        valuta=valuta,
        reale=reale,
    )

with st.sidebar:
    st.header("Parametri")
    valuta = st.selectbox(
        "Valuta", ["USD", "EUR"], index=0, key="valuta",
        format_func=lambda v: f"{SIMBOLI[v]}  {v} — {ETICHETTE[v]}",
        help="I dati di partenza sono in dollari. Cambiando valuta si convertono i prezzi, "
             "non solo il risultato: costi, imposte e ribilanciamenti avvengono nella "
             "valuta scelta, come per chi compra strumenti denominati in euro. "
             "Prima del 1999 il cambio euro/dollaro è ricostruito dalla lira (1936,27 "
             "lire per euro) con dati mensili: è la convenzione dell'euro sintetico.")
    min_date_valuta = _minimo_ammesso(valuta)
    reale = st.checkbox(
        "Al netto dell'inflazione italiana", value=False, key="reale",
        help="Toglie l'effetto dell'inflazione italiana (indice HICP di Eurostat, "
             "ricostruito dal 1956): le curve restano nel potere d'acquisto della prima "
             "data simulata, non in quello di oggi.")
    initial_value = st.number_input(
        f"Capitale iniziale ({SIMBOLI[valuta]})", min_value=100.0, value=10_000.0, step=1_000.0)
    orizzonte_auto = st.checkbox(
        "Orizzonte automatico", value=True, key="orizzonte_auto",
        help="Usa la finestra più lunga in cui TUTTI gli strumenti scelti hanno un prezzo: "
             "l'inizio è la più recente fra le date di partenza degli strumenti, la fine è "
             "l'ultima data disponibile. Non serve per la volatilità di un singolo strumento: "
             "serve perché un asset che parte dopo accorcia la storia comune a tutto il "
             "portafoglio (issue #8).")
    if orizzonte_auto:
        begin_date, end_date = None, None
    else:
        # Se il bottone sotto l'errore ha chiesto di rientrare nella finestra, la richiesta
        # va applicata PRIMA che i widget esistano: dopo, Streamlit non permette di
        # riscriverne il valore ("cannot be modified after the widget is instantiated").
        if "chiedi_finestra" in st.session_state:
            _primo, _ultimo = st.session_state.pop("chiedi_finestra")
            st.session_state["data_inizio"] = _primo
            st.session_state["data_fine"] = _ultimo
        st.session_state.setdefault("data_inizio", max(min_date_valuta, pd.Timestamp("2001-01-01").date()))
        st.session_state.setdefault("data_fine", min(max_date, pd.Timestamp("2025-09-01").date()))
        begin_date = st.date_input(
            "Data iniziale",
            key="data_inizio",
            min_value=min_date_valuta, max_value=max_date,
            help=f"Il calendario mostra dieci anni avanti e indietro dalla data scelta: per "
                 f"andare più indietro **scrivi l'anno nel campo** (o usa le frecce ←→). "
                 f"I dati arrivano dal {min_date_valuta} al {max_date}"
                 + (" (il cambio comincia nel 1971: prima di allora i valori in euro o lire "
                    "non esistono)" if valuta != "USD" else "")
                 + ". Per partire dal primo giorno disponibile usa «Orizzonte automatico».")
        end_date = st.date_input(
            "Data finale",
            key="data_fine",
            min_value=min_date, max_value=max_date,
            help=f"Il calendario mostra dieci anni avanti e indietro dalla data scelta: per "
                 f"una data più lontana **scrivi l'anno nel campo** (o usa le frecce ←→). "
                 f"I dati arrivano fino al {max_date}.")
    brokerage_pct = st.number_input(
        "Costi di negoziazione (%)", min_value=0.0, max_value=10.0, value=0.1, step=0.01,
        key="glob_comm", on_change=applica_colonna("Commissione (%)", "glob_comm"),
        help="Commissione del broker, per operazione."
             "Cambiandola si applica a tutti gli strumenti.")
    annual_costs_pct = st.number_input(
        "Costi annui (%)", min_value=0.0, max_value=10.0, value=0.2, step=0.01,
        key="glob_costi", on_change=applica_colonna("Costi annui (%)", "glob_costi"),
        help="Tutto il costo annuo di detenzione: imposta di bollo (0,20%) ed eventuali costi "
             "di piattaforma. Il TER degli ETF è già dentro le serie dei prezzi.")
    tax_pct = st.number_input(
        "Aliquota fiscale (%)", min_value=0.0, max_value=100.0, value=26.0, step=0.1,
        key="glob_aliquota", on_change=applica_colonna("Aliquota (%)", "glob_aliquota"),
        help="26% sui guadagni ordinari, 12,5% sui titoli di Stato white list. Il valore "
             "precompilato per ogni strumento si può cambiare nella tabella.")
    rebalance_pct = st.number_input(
        "Soglia di ribilanciamento assoluta (%)", min_value=0.1, max_value=100.0, value=5.0, step=0.5,
        help="Scostamento misurato in punti di peso. Con 5%, un comparto al 50% viene "
             "riportato a target quando arriva al 55% o scende al 45%. Il ribilanciamento "
             "scatta quando lo scostamento supera QUESTO valore oppure la soglia "
             "relativa: basta che una delle due sia superata.")
    rel_rebalance_pct = st.number_input(
        "Soglia di ribilanciamento relativa (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0,
        help="Scostamento misurato in percentuale del peso obiettivo di ciascuno "
             "strumento. Con 20%, un comparto al 5% viene riportato a target quando "
             "arriva al 6% o scende al 4%. Il ribilanciamento scatta quando lo "
             "scostamento supera QUESTA percentuale oppure la soglia assoluta: basta "
             "che una delle due sia superata. 0 = soglia relativa disattivata.")
    st.button("Applica i valori globali a tutti gli strumenti", on_click=applica_valori_globali,
              width="stretch",
              help="Sovrascrive commissione, costi annui e aliquota di ogni riga con i tre "
                   "valori qui sopra. Le modifiche fatte a mano nella tabella vanno perse.")

st.button("Azzera le allocazioni", on_click=azzera_allocazione, width="stretch",
          help="Riporta a zero la colonna «Allocazione (%)»: l'app non propone pesi, "
               "li scrivi tu. Commissioni, costi e aliquote restano quelli impostati.")

# Una sola tabella per strumento: allocazione e i tre costi (#73). L'allocazione parte da
# zero: l'app non suggerisce pesi. Costi e aliquote partono dai campi generali della barra
# laterale, tranne l'aliquota dei Treasury che parte dal 12,5% di legge. La tabella vive in
# session_state perché «azzera» e «applica a tutti» la riscrivono prima che il widget esista.
if CHIAVE_TABELLA not in st.session_state:
    st.session_state[CHIAVE_TABELLA] = pd.DataFrame(
        {
            "Strumento": assets,
            "Allocazione (%)": [0.0] * len(assets),
            "Commissione (%)": [float(brokerage_pct)] * len(assets),
            "Costi annui (%)": [float(annual_costs_pct)] * len(assets),
            "Aliquota (%)": [ALIQUOTA_SOVRANA if asset in STRUMENTI_SOVRANI else float(tax_pct)
                             for asset in assets],
        }
    ).set_index("Strumento")

# La tabella ha una `key` versionata: cambiando la versione si crea un widget nuovo, che
# riparte dai dati passati. Serve perche' `st.data_editor` NON accetta aggiornamenti via
# session_state (`writes_allowed=False`: alzerebbe StreamlitValueAssignmentNotAllowedError),
# quindi i preset e "applica a tutti" non possono scrivere nello stato del widget: possono
# solo chiedere un editor nuovo, e lo fanno incrementando la versione.
#
# La versione NON cambia quando l'utente modifica una cella, quindi fra un run e l'altro
# l'editor e' lo stesso widget e la modifica resta sua: e' il caso che prima si perdeva al
# primo invio, perche' senza key l'identita' del widget cambiava a ogni giro e la modifica
# appena digitata non aveva piu' un posto dove stare.
versione = st.session_state.setdefault("versione_tabella", 0)
tabella = st.data_editor(
    st.session_state[CHIAVE_TABELLA],
    key=f"editor_asset_{versione}",
    width="stretch",
    num_rows="fixed",
    column_config={
        "Allocazione (%)": st.column_config.NumberColumn(
            "Allocazione (%)", min_value=0, max_value=100, step=1, format="%d",
            help="Peso nel portafoglio. Percentuale intera: i mezzi punti sono rumore."),
        "Commissione (%)": st.column_config.NumberColumn(
            "Commissione (%)", min_value=0.0, max_value=10.0, step=0.01, format="%.2f",
            help="Commissione del broker per operazione su questo strumento."),
        "Costi annui (%)": st.column_config.NumberColumn(
            "Costi annui (%)", min_value=0.0, max_value=10.0, step=0.01, format="%.2f",
            help="Costo di detenzione annuo: bollo e piattaforma. Il TER è già nelle serie con suffisso SIM."),
        "Aliquota (%)": st.column_config.NumberColumn(
            "Aliquota (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.1f",
            help="12,5% sui titoli di Stato white list, 26% sul resto."),
    },
)
st.session_state[CHIAVE_TABELLA] = tabella

allocazione = tabella["Allocazione (%)"].astype(float)
total_weight = float(allocazione.sum())
attivi = {asset: peso for asset, peso in allocazione.items() if peso > 0}
if not attivi:
    st.warning("Nessuno strumento con allocazione maggiore di zero: il backtest non ha niente da simulare.")

st.metric("Totale allocazione", f"{total_weight:.0f}%")

finestra_anni = None
if orizzonte_auto and attivi:
    finestra = finestra_comune(attivi)
    if finestra:
        inizio, fine, chi = finestra
        anni = (fine - inizio).days / 365.25
        finestra_anni = anni
        st.caption(
            f"Orizzonte automatico: dal **{inizio.date()}** al **{fine.date()}** "
            f"({anni:.1f} anni). L'inizio lo decide **{chi}**, lo strumento che parte più "
            f"tardi; la fine è la data più recente comune a tutti."
        )
    else:
        st.warning("Nessuno strumento attivo ha una serie di prezzi: finestra non calcolabile.")
if attivi and total_weight != 100:
    st.warning(f"L'allocazione somma a {total_weight:.0f}% e non a 100%: correggila prima di eseguire.")

# Orizzonte breve, dichiarato PRIMA di eseguire (issue #88). La finestra non si stima
# dalle date scelte: si chiede al motore quale simulerebbe davvero con questi ingressi
# (`anni_simulati` usa la stessa regola di `backtest()`), così l'avviso compare negli
# stessi casi in cui il motore lo metterebbe nel riepilogo. Se il motore non sa ancora
# calcolare la finestra (date invertite, strumenti senza prezzi) non c'è niente da dire:
# ci pensa l'errore corrispondente.
if attivi:
    _anni_motore = anni_simulati(raw, list(attivi), begin_date, end_date)
    _avviso_orizzonte = messaggio_orizzonte_breve(_anni_motore)
    if _avviso_orizzonte:
        st.warning(_avviso_orizzonte)

# La finestra chiesta esce da quella coperta dagli strumenti attivi: si dice quale la
# limita e si offre il rimedio in un clic. Il bottone sta qui, nel flusso normale, e non
# dentro il tasto «Esegui»: dentro esisterebbe solo nel run in cui hai premuto Esegui, e
# premendolo da solo non eseguirebbe nulla.
if attivi and not orizzonte_auto:
    _finestra = finestra_comune(attivi)
    if _finestra:
        _primo, _ultimo, _chi = _finestra[0].date(), _finestra[1].date(), _finestra[2]
        _fuori_inizio = begin_date < _primo
        _fuori_fine = end_date > _ultimo
        if _fuori_inizio or _fuori_fine:
            _quale = ("iniziale" if _fuori_inizio else "") + (" e " if _fuori_inizio and _fuori_fine else "") + \
                     ("finale" if _fuori_fine else "")
            st.error(
                f"**{_chi}** ha dati dal **{_primo}** al **{_ultimo}**: la data {_quale} scelta "
                f"({begin_date} – {end_date}) esce da lì, quindi il backtest non può partire."
            )
            if st.button(f"Restringi al {_primo} – {_ultimo}", key="restringi_finestra",
                         help="Riporta inizio e fine dentro i giorni in cui TUTTI gli "
                              "strumenti attivi hanno un prezzo."):
                st.session_state["chiedi_finestra"] = (_primo, _ultimo)
                st.rerun()

# I risultati restano in sessione: senza questo, cambiare una vista (per esempio la scala
# del grafico) fa ripartire lo script con il bottone non premuto, e la tabella sparisce.
CHIAVE_RISULTATI = "ultimi_risultati"
_errore = None

if st.button("Esegui backtest", type="primary", width="stretch"):
    if not orizzonte_auto and begin_date >= end_date:
        _errore = "La data iniziale deve precedere la data finale."
    elif total_weight != 100:
        _errore = f"L'allocazione deve sommare a 100%. Totale attuale: {total_weight:.0f}%."
    elif not attivi:
        _errore = "Nessuno strumento con allocazione maggiore di zero."
    else:
        # Solo gli strumenti con peso > 0 entrano nella simulazione, ognuno con i propri
        # costi e la propria aliquota (#73, AC3).
        weights = {asset: peso / 100.0 for asset, peso in attivi.items()}
        commissioni = {asset: float(tabella.loc[asset, "Commissione (%)"]) / 100.0 for asset in attivi}
        costi_annui = {asset: float(tabella.loc[asset, "Costi annui (%)"]) / 100.0 for asset in attivi}
        aliquote = {asset: float(tabella.loc[asset, "Aliquota (%)"]) / 100.0 for asset in attivi}
        try:
            with st.spinner("Esecuzione del backtest..."):
                _risultati = esegui_backtest(
                    initial_value=initial_value,
                    weights=weights,
                    begin_date=pd.Timestamp(begin_date) if begin_date is not None else None,
                    end_date=pd.Timestamp(end_date) if end_date is not None else None,
                    commissioni=commissioni,
                    costi_annui=costi_annui,
                    aliquote=aliquote,
                    soglia_ribilanciamento=rebalance_pct / 100.0,
                    # Soglia relativa in OR con quella assoluta: un comparto piccolo
                    # viene riportato a target prima di dover raddoppiare. 0 = spenta.
                    soglia_ribilanciamento_relativa=(rel_rebalance_pct / 100.0) if rel_rebalance_pct > 0 else None,
                    valuta=valuta,
                    reale=reale,
                )
        except Exception as errore:  # noqa: BLE001
            # Un errore del motore è un messaggio per chi usa l'app, non un traceback.
            # Si cattura qualunque eccezione, non solo ValueError: su Streamlit Cloud il
            # testo delle eccezioni non gestite viene oscurato ("redacted"), e un TypeError
            # senza messaggio è indistinguibile da un guasto dell'app.
            _errore = f"Il backtest non può partire: {type(errore).__name__}: {errore}"
        else:
            st.session_state[CHIAVE_RISULTATI] = _risultati

if _errore:
    st.error(_errore)
    st.session_state.pop(CHIAVE_RISULTATI, None)

# Un errore nuovo invalida i risultati vecchi: mostrarli accanto al messaggio farebbe
# credere che il numero sbagliato sia quello giusto.
if not _errore and CHIAVE_RISULTATI in st.session_state:
    df_log, df_delta, summary = st.session_state[CHIAVE_RISULTATI]
    # Tabella comparativa dei tre portafogli (issue #75).
    # Le metriche NON si ricalcolano qui: il motore le produce già per tutte e tre le
    # curve (summary["risk_metrics"]["gross"|"broker"|"net"]) con la stessa metodologia.
    # Questa sezione si limita a disporle in righe, una per portafoglio.
    def _percentuale(valore):
        return "n.d." if valore is None else f"{valore * 100:.2f}%"

    def _numero(valore):
        return "n.d." if valore is None else f"{valore:.2f}"

    metriche_tre_portafogli = []
    for chiave, etichetta in (("gross", "Lordo"), ("broker", "Broker"), ("net", "Netto")):
        m = (summary.get("risk_metrics") or {}).get(chiave) or {}
        metriche_tre_portafogli.append({
            "Portafoglio": etichetta,
            "CAGR": _percentuale(summary.get(f"cagr_{chiave}")),
            "Valore finale": f"{SIMBOLI[summary.get('valuta', 'USD')]} {summary[f'final_{chiave}']:,.2f}",
            "Volatilità annua": _percentuale(m.get("volatility")),
            "Max drawdown": _percentuale(m.get("max_drawdown")),
            f"Sharpe (rf={summary.get('risk_free_rate', 0.0) * 100:.2f}%)": _numero(m.get("sharpe")),
            "Sortino": _numero(m.get("sortino")),
            "Ulcer index": _percentuale(m.get("ulcer_index")),
            "Calmar": _numero(m.get("calmar")),
        })
    st.dataframe(pd.DataFrame(metriche_tre_portafogli), hide_index=True, width="stretch")
    st.caption(
        "Le tre righe sono le stesse operazioni lette su tre curve di equity: il lordo non "
        "paga nulla, il broker paga commissioni e costi e fiscalità (solo quando c'è un ribilanciamento), "
        "il netto paga le imposte ipotizzando la liquidazione totale del portafoglio. "
        "La differenza fra le righe è quindi l'effetto di costi e fiscalità."
    )
    st.caption(
        f"Simulato dal **{summary['begin_date'].date()}** al **{summary['end_date'].date()}** "
        f"({summary['years']:.2f} anni), capitale iniziale {initial_value:,.0f} "
        f"{SIMBOLI[summary.get('valuta', 'USD')]}."
    )
    if summary.get("valuta", "USD") != "USD" or summary.get("reale"):
        _valuta_riga = "euro" if summary["valuta"] == "EUR" else "dollari"
        _nota = (f"Valori in **{_valuta_riga}**: il cambio è applicato ai prezzi, quindi "
                 "ribilanciamenti e imposte ragionano nella valuta scelta.")
        if summary.get("reale"):
            _nota += (" Al netto dell'inflazione italiana: le curve sono nel potere "
                      "d'acquisto della prima data simulata, non in quello di oggi.")
        if summary["valuta"] != "USD" and summary["begin_date"] < pd.Timestamp("1999-01-01"):
            _nota += (" Prima del 1999 l'euro non esisteva: il cambio è ricostruito dalla "
                      "lira a 1936,27 lire per euro, con dati mensili riportati in avanti.")
        st.caption(_nota)
    st.caption(
        f"Sharpe e Sortino usano {summary.get('risk_free_rate_source', '0')} come tasso privo di "
        f"rischio: nel periodo ha reso in media {summary.get('risk_free_rate', 0.0) * 100:.2f}% "
        "l'anno, giorno per giorno. Con un tasso a zero i due rapporti sarebbero più alti "
        "e non confrontabili fra periodi con tassi diversi."
    )

    chart_cols = [c for c in ["GrossPortfolioValue", "BrokerPortfolioValue", "Net"] if c in df_log.columns]
    if chart_cols:
        scala_log = st.checkbox(
            "Scala logaritmica", value=False, key="scala_log",
            help="Su una scala logaritmica la stessa distanza verticale vale la stessa "
                 "variazione percentuale: un raddoppio si vede uguale sia partendo da "
                 "10.000 sia da 100.000. Serve a leggere la crescita composta, che su "
                 "una scala lineare diventa una curva che sembra esplodere alla fine.")
        if scala_log:
            # Streamlit non ha una scala logaritmica nativa per line_chart: la curva
            # lunga passa ad Altair, che la supporta nativamente. I valori sono gli
            # stessi tre delle altre viste.
            lungo = df_log[chart_cols].reset_index()
            colonna_data = lungo.columns[0]
            lungo = lungo.melt(id_vars=colonna_data, var_name="Serie", value_name="Valore")
            positivo = lungo[lungo["Valore"] > 0]
            grafico = (
                alt.Chart(positivo)
                .mark_line()
                .encode(
                    x=alt.X(f"{colonna_data}:T", title=None),
                    y=alt.Y("Valore:Q", title=None, scale=alt.Scale(type="log")),
                    color=alt.Color("Serie:N", title=None),
                )
                .properties(height=420)
            )
            st.altair_chart(grafico, use_container_width=True)
            if len(positivo) < len(lungo):
                st.caption("In scala logaritmica i valori non positivi non sono rappresentabili "
                           "e sono stati esclusi dal grafico.")
        else:
            st.line_chart(df_log[chart_cols])

    st.download_button(
        "Scarica risultati Excel",
        data=to_excel_bytes(df_log, df_delta),
        file_name="portfolio_backtest.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    with st.expander("Anteprima risultati"):
        st.dataframe(df_log.tail(100), width="stretch")

# Perimetro dichiarato. Sta in fondo perché chi apre la pagina vuole prima calcolare; ma
# resta completo, e i test lo sorvegliano: lo strumento didattico non è consulenza, non
# contiene raccomandazioni, e i limiti del calcolo sono dichiarati.
st.divider()
st.caption(
    "**Strumento didattico.** Calcola cosa sarebbe successo a un portafoglio definito da te "
    "sui dati storici di questo dataset. Non è consulenza in materia di investimenti e non "
    "contiene raccomandazioni né previsioni. I rendimenti passati non predicono quelli futuri."
)
st.caption(
    "Limiti: le minusvalenze non sono compensate, i valori sono in dollari statunitensi "
    "salvo diversa scelta, le serie con suffisso SIM sono ricostruite e non strumenti "
    "negoziabili."
)

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from backtester import backtest

st.set_page_config(page_title="Portfolio Backtester", page_icon="📈", layout="wide")
st.title("Portfolio Backtester")
st.caption("Configura online asset allocation, periodo, costi, soglia di ribilanciamento e fiscalità.")

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

# Portafoglio che l'app carica all'apertura. Il preset "Attuale" legge DA QUI, non da una
# copia: prima erano due dizionari separati e si erano gia' disallineati (il preset diceva
# 60/10/25/5 con ZROZ al 25%, il default era 60/10/20/10 con IEF al 20%: caricare "Attuale"
# cambiava il portafoglio invece di riportarlo all'inizio).
DEFAULT_PESI = {"VTSIM": 60.0, "GLDSIM": 10.0, "IEFSIM": 20.0, "DBMFSIM": 10.0}

# Portafogli pronti: approssimazioni costruite con gli asset disponibili nel dataset.
# I nomi restano corti; la composizione la scrive `composizione_preset()` con i nomi degli
# strumenti, perche' "60/10/20/10" non dice a quale strumento corrisponde ogni percentuale
# (issue #85).
PRESET = {
    "Attuale": DEFAULT_PESI,
    "Classico 60/40": {"VTSIM": 60.0, "IEFSIM": 40.0},
    "Permanent Portfolio": {"VTSIM": 25.0, "TLTSIM": 25.0, "GLDSIM": 25.0, "CASHX": 25.0},
    "All weather": {"VTSIM": 30.0, "TLTSIM": 40.0, "IEFSIM": 15.0, "GLDSIM": 15.0},
    "Golden butterfly": {"VTSIM": 40.0, "TLTSIM": 20.0, "SHYSIM": 20.0, "GLDSIM": 20.0},
    "Solo azionario globale": {"VTSIM": 100.0},
}


def composizione_preset(nome):
    """«60% VTSIM (azionario globale) · 10% GLDSIM (oro fisico) · …» per il preset scelto."""
    pezzi = []
    for asset, peso in PRESET[nome].items():
        if float(peso) > 0:
            nome_leggibile = ASSET_INFO.get(asset, (asset, ""))[0]
            pezzi.append(f"{float(peso):.0f}% {asset} ({nome_leggibile})")
    return " · ".join(pezzi)


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


def carica_preset(nome):
    """Imposta le allocazioni del preset; gira PRIMA che la tabella esista (on_click)."""
    if CHIAVE_TABELLA not in st.session_state:
        return
    tabella = st.session_state[CHIAVE_TABELLA].copy()
    tabella["Allocazione (%)"] = [int(PRESET[nome].get(asset, 0.0)) for asset in tabella.index]
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


DATA_FILE = Path(__file__).with_name("Timeseries.csv")
raw = pd.read_csv(DATA_FILE, sep=";")
raw["Date"] = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce")
raw = raw.dropna(subset=["Date"])
assets = [c for c in raw.columns if c != "Date"]
min_date = raw["Date"].min().date()
max_date = raw["Date"].max().date()

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
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_log.to_excel(writer, sheet_name="Portfolio")
        df_delta.to_excel(writer, sheet_name="Rebalancing")
    return buffer.getvalue()

with st.sidebar:
    st.header("Parametri")
    initial_value = st.number_input("Capitale iniziale ($)", min_value=100.0, value=10_000.0, step=1_000.0)
    orizzonte_auto = st.checkbox(
        "Orizzonte automatico", value=False, key="orizzonte_auto",
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
        st.session_state.setdefault("data_inizio", max(min_date, pd.Timestamp("2001-01-01").date()))
        st.session_state.setdefault("data_fine", min(max_date, pd.Timestamp("2025-09-01").date()))
        begin_date = st.date_input(
            "Data iniziale",
            key="data_inizio",
            min_value=min_date, max_value=max_date,
            help=f"Il calendario mostra dieci anni avanti e indietro dalla data scelta: per "
                 f"andare più indietro **scrivi l'anno nel campo** (o usa le frecce ←→). "
                 f"I dati arrivano dal {min_date} al {max_date}. Per partire dal primo giorno "
                 f"disponibile usa «Orizzonte automatico».")
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
    rebalance_pct = st.number_input("Soglia di ribilanciamento assoluta (%)", min_value=0.1, max_value=100.0, value=5.0, step=0.5)
    st.button("Applica i valori globali a tutti gli strumenti", on_click=applica_valori_globali,
              width="stretch",
              help="Sovrascrive commissione, costi annui e aliquota di ogni riga con i tre "
                   "valori qui sopra. Le modifiche fatte a mano nella tabella vanno perse.")

scelta_preset = st.selectbox("Portafoglio predefinito", list(PRESET),
    help="Approssimazioni costruite con gli asset disponibili in questo dataset.")
st.caption(f"Composizione di «{scelta_preset}»: {composizione_preset(scelta_preset)}")
st.button("Carica il portafoglio predefinito", on_click=carica_preset,
          args=(scelta_preset,), width="stretch",
          help="Riscrive la colonna dell'allocazione con i pesi del portafoglio scelto.")
defaults = DEFAULT_PESI

# Una sola tabella per strumento: allocazione e i tre costi (#73). I valori iniziali
# vengono dai campi generali della barra laterale, tranne l'aliquota dei Treasury che parte
# dal 12,5% di legge. La tabella vive in session_state perché i preset e il bottone
# "applica a tutti" la riscrivono prima che il widget esista.
if CHIAVE_TABELLA not in st.session_state:
    st.session_state[CHIAVE_TABELLA] = pd.DataFrame(
        {
            "Strumento": assets,
            "Allocazione (%)": [float(defaults.get(asset, 0.0)) for asset in assets],
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

if orizzonte_auto and attivi:
    finestra = finestra_comune(attivi)
    if finestra:
        inizio, fine, chi = finestra
        anni = (fine - inizio).days / 365.25
        st.caption(
            f"Orizzonte automatico: dal **{inizio.date()}** al **{fine.date()}** "
            f"({anni:.1f} anni). L'inizio lo decide **{chi}**, lo strumento che parte più "
            f"tardi; la fine è la data più recente comune a tutti."
        )
    else:
        st.warning("Nessuno strumento attivo ha una serie di prezzi: finestra non calcolabile.")
if attivi and total_weight != 100:
    st.warning(f"L'allocazione somma a {total_weight:.0f}% e non a 100%: correggila prima di eseguire.")

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

if st.button("Esegui backtest", type="primary", width="stretch"):
    if not orizzonte_auto and begin_date >= end_date:
        st.error("La data iniziale deve precedere la data finale.")
    elif total_weight != 100:
        st.error(f"L'allocazione deve sommare a 100%. Totale attuale: {total_weight:.0f}%.")
    elif not attivi:
        st.error("Nessuno strumento con allocazione maggiore di zero.")
    else:
        # Solo gli strumenti con peso > 0 entrano nella simulazione, ognuno con i propri
        # costi e la propria aliquota (#73, AC3).
        weights = {asset: peso / 100.0 for asset, peso in attivi.items()}
        commissioni = {asset: float(tabella.loc[asset, "Commissione (%)"]) / 100.0 for asset in attivi}
        costi_annui = {asset: float(tabella.loc[asset, "Costi annui (%)"]) / 100.0 for asset in attivi}
        aliquote = {asset: float(tabella.loc[asset, "Aliquota (%)"]) / 100.0 for asset in attivi}
        try:
            with st.spinner("Esecuzione del backtest..."):
                df_log, df_delta, summary = backtest(
                    initial_value=initial_value,
                    weights=weights,
                    begin_date=pd.Timestamp(begin_date) if begin_date is not None else None,
                    end_date=pd.Timestamp(end_date) if end_date is not None else None,
                    brokerage_fee_rate=commissioni,
                    rebalance_threshold=rebalance_pct / 100.0,
                    tax_rate=aliquote,
                    annual_costs_rate=costi_annui,
                    # Sharpe e Sortino con il cash a 3 mesi come tasso privo di rischio
                    # (issue #79). Con rf=0 il rapporto era sovrastimato: nel periodo
                    # 2010-2025 il cash ha reso in media 1,33% l'anno.
                    risk_free_rate="CASHX",
                    plot=False,
                    save_outputs=False,
                )
        except ValueError as errore:
            # Un errore del motore è un messaggio per chi usa l'app, non un traceback.
            st.error(f"Il backtest non può partire: {errore}")
            st.stop()

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
                "Valore finale": f"$ {summary[f'final_{chiave}']:,.2f}",
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
            f"({summary['years']:.2f} anni), capitale iniziale {initial_value:,.0f}."
        )
        st.caption(
            f"Sharpe e Sortino usano {summary.get('risk_free_rate_source', '0')} come tasso privo di "
            f"rischio: nel periodo ha reso in media {summary.get('risk_free_rate', 0.0) * 100:.2f}% "
            "l'anno, giorno per giorno. Con un tasso a zero i due rapporti sarebbero più alti "
            "e non confrontabili fra periodi con tassi diversi."
        )

        chart_cols = [c for c in ["GrossPortfolioValue", "BrokerPortfolioValue", "Net"] if c in df_log.columns]
        if chart_cols:
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

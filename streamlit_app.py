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

# Portafogli pronti: approssimazioni costruite con gli asset disponibili nel dataset.
PRESET = {
    "Attuale (60/10/25/5)": {"VTSIM": 60.0, "GLDSIM": 10.0, "ZROZSIM": 25.0, "DBMFSIM": 5.0},
    "Classico 60/40": {"VTSIM": 60.0, "IEFSIM": 40.0},
    "Permanent Portfolio": {"VTSIM": 25.0, "TLTSIM": 25.0, "GLDSIM": 25.0, "CASHX": 25.0},
    "All weather": {"VTSIM": 30.0, "TLTSIM": 40.0, "IEFSIM": 15.0, "GLDSIM": 15.0},
    "Golden butterfly": {"VTSIM": 40.0, "TLTSIM": 20.0, "SHYSIM": 20.0, "GLDSIM": 20.0},
    "Solo azionario globale": {"VTSIM": 100.0},
}


# Aliquote di partenza per strumento: 12,5% sui titoli di Stato white list (base ridotta al
# 48,08%: 0,4808 x 26% = 12,5%), 26% su tutto il resto. E' un DEFAULT modificabile in tabella,
# non una regola cablata nel motore: quello che l'utente vede e' quello che viene applicato.
STRUMENTI_SOVRANI = {"SHYSIM", "IEFSIM", "TLTSIM", "ZROZSIM"}
ALIQUOTA_SOVRANA = 12.5

CHIAVE_TABELLA = "tabella_per_asset"


def carica_preset(nome):
    """Imposta le allocazioni del preset; gira PRIMA che la tabella esista (on_click)."""
    if CHIAVE_TABELLA not in st.session_state:
        return
    tabella = st.session_state[CHIAVE_TABELLA].copy()
    tabella["Allocazione (%)"] = [int(PRESET[nome].get(asset, 0.0)) for asset in tabella.index]
    st.session_state[CHIAVE_TABELLA] = tabella


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


DATA_FILE = Path(__file__).with_name("Timeseries.csv")
raw = pd.read_csv(DATA_FILE, sep=";")
raw["Date"] = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce")
raw = raw.dropna(subset=["Date"])
assets = [c for c in raw.columns if c != "Date"]
min_date = raw["Date"].min().date()
max_date = raw["Date"].max().date()

def to_excel_bytes(df_log, df_delta):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_log.to_excel(writer, sheet_name="Portfolio")
        df_delta.to_excel(writer, sheet_name="Rebalancing")
    return buffer.getvalue()

with st.sidebar:
    st.header("Parametri")
    initial_value = st.number_input("Capitale iniziale ($)", min_value=100.0, value=10_000.0, step=1_000.0)
    begin_date = st.date_input("Data iniziale", value=max(min_date, pd.Timestamp("2001-01-01").date()), min_value=min_date, max_value=max_date)
    end_date = st.date_input("Data finale", value=min(max_date, pd.Timestamp("2025-09-01").date()), min_value=min_date, max_value=max_date)
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
st.button("Carica il portafoglio predefinito", on_click=carica_preset,
          args=(scelta_preset, assets), width="stretch")
defaults = {"VTSIM": 60.0, "GLDSIM": 10.0, "IEFSIM": 20.0, "DBMFSIM": 10.0}

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

# Nessuna `key` sul widget: il valore vive in `CHIAVE_TABELLA`, che i callback riscrivono
# prima che l'editor esista. Passare insieme `data=` e `key=` fa scattare il controllo di
# Streamlit sulle due sorgenti di verita' (StreamlitAPIException).
tabella = st.data_editor(
    st.session_state[CHIAVE_TABELLA],
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
if attivi and total_weight != 100:
    st.warning(f"L'allocazione somma a {total_weight:.0f}% e non a 100%: correggila prima di eseguire.")

if st.button("Esegui backtest", type="primary", width="stretch"):
    if begin_date >= end_date:
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
        with st.spinner("Esecuzione del backtest..."):
            df_log, df_delta, summary = backtest(
                initial_value=initial_value,
                weights=weights,
                begin_date=pd.Timestamp(begin_date),
                end_date=pd.Timestamp(end_date),
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

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from backtester import backtest

st.set_page_config(page_title="Portfolio Backtester", page_icon="📈", layout="wide")
st.title("Portfolio Backtester")
st.caption("Configura online asset allocation, periodo, costi, soglia di ribilanciamento e fiscalità.")

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
    initial_value = st.number_input("Capitale iniziale (€)", min_value=100.0, value=10_000.0, step=1_000.0)
    begin_date = st.date_input("Data iniziale", value=max(min_date, pd.Timestamp("2010-01-02").date()), min_value=min_date, max_value=max_date)
    end_date = st.date_input("Data finale", value=min(max_date, pd.Timestamp("2025-09-01").date()), min_value=min_date, max_value=max_date)
    brokerage_pct = st.number_input("Costi di negoziazione (%)", min_value=0.0, max_value=10.0, value=0.29, step=0.01)
    annual_costs_pct = st.number_input("Costi annui (%)", min_value=0.0, max_value=10.0, value=0.0, step=0.01)
    tax_pct = st.number_input("Aliquota fiscale (%)", min_value=0.0, max_value=100.0, value=26.0, step=0.5)
    rebalance_pct = st.number_input("Soglia di ribilanciamento (%)", min_value=0.1, max_value=100.0, value=10.0, step=0.5)

st.subheader("Asset allocation")
defaults = {"VTSIM": 60.0, "GLDSIM": 10.0, "ZROZSIM": 25.0, "DBMFSIM": 5.0}
cols = st.columns(3)
weights_pct = {}
for i, asset in enumerate(assets):
    with cols[i % 3]:
        weights_pct[asset] = st.number_input(f"{asset} (%)", min_value=0.0, max_value=100.0, value=float(defaults.get(asset, 0.0)), step=1.0, key=f"w_{asset}")

# Asset per cui la quota ha senso: solo quelli che possono contenere titoli di Stato.
# Azionario, oro, liquidita' e managed futures non possono averne, quindi la quota e' 0 per
# costruzione e non c'e' niente da chiedere all'utente (un campo in piu' sarebbe solo rumore).
# I Treasury USA sono white list: sui quattro ETF Treasury del dataset la quota e' 100%.
# Se un domani si aggiunge un ETF obbligazionario aggregate, va messo qui con la sua quota
# certificata dall'emittente.
GOV_CAPABLE = {"SHYSIM": 100.0, "IEFSIM": 100.0, "TLTSIM": 100.0, "ZROZSIM": 100.0}

with st.expander("Fiscalità per asset — quota titoli di Stato white list"):
    st.caption(
        "Sulla quota di provento riferibile a titoli di Stato white list la base imponibile è "
        "ridotta al 48,08%: aliquota effettiva 12,5% su quella parte, 26% sul resto. "
        "I Treasury USA sono white list. La percentuale è quella certificata dall'emittente: "
        "se il fondo non la pubblica, il broker applica il 26% pieno."
    )
    gov_pct = {a: 0.0 for a in assets}
    obbligazionari = [a for a in assets if a in GOV_CAPABLE]
    colonne_gov = st.columns(max(1, min(3, len(obbligazionari))))
    for i, asset in enumerate(obbligazionari):
        with colonne_gov[i % len(colonne_gov)]:
            gov_pct[asset] = st.number_input(
                f"{asset} — quota Stato (%)", min_value=0.0, max_value=100.0,
                value=float(GOV_CAPABLE[asset]), step=5.0, key=f"g_{asset}",
                help="Quota di titoli di Stato white list certificata dall'emittente.")
    altri = [a for a in assets if a not in GOV_CAPABLE]
    if altri:
        st.caption("Per gli altri asset la quota non è richiesta: azionario, oro, liquidità e "
                   "managed futures non possono contenere titoli di Stato, quindi restano al 26%.")

    aliquota_su = tax_pct / 100.0
    con_quota = [a for a in assets if gov_pct.get(a, 0.0) > 0]
    if con_quota:
        dettaglio = " · ".join(
            f"{a} {((1 - gov_pct[a] / 100.0) * aliquota_su + (gov_pct[a] / 100.0) * 0.125) * 100:.2f}%"
            for a in con_quota)
        senza = len(assets) - len(con_quota)
        st.caption(f"Aliquota effettiva: {dettaglio}" + (f" · gli altri {senza} asset al {aliquota_su*100:.2f}%" if senza else ""))
    else:
        st.caption(f"Nessuna quota dichiarata: tutti gli asset al {aliquota_su*100:.2f}%.")

total_weight = sum(weights_pct.values())
st.metric("Totale allocazione", f"{total_weight:.2f}%")

if st.button("Esegui backtest", type="primary", use_container_width=True):
    if begin_date >= end_date:
        st.error("La data iniziale deve precedere la data finale.")
    elif abs(total_weight - 100.0) > 0.01:
        st.error(f"L'allocazione deve sommare a 100%. Totale attuale: {total_weight:.2f}%.")
    else:
        weights = {asset: value / 100.0 for asset, value in weights_pct.items()}
        with st.spinner("Esecuzione del backtest..."):
            df_log, df_delta, summary = backtest(
                initial_value=initial_value,
                weights=weights,
                begin_date=pd.Timestamp(begin_date),
                end_date=pd.Timestamp(end_date),
                brokerage_fee_rate=brokerage_pct / 100.0,
                rebalance_threshold=rebalance_pct / 100.0,
                tax_rate=tax_pct / 100.0,
                gov_share={a: v / 100.0 for a, v in gov_pct.items()},
                annual_costs_rate=annual_costs_pct / 100.0,
                plot=False,
                save_outputs=False,
            )

        risk = (summary.get("risk_metrics") or {}).get("net") or {}
        r1, r2, r3 = st.columns(3)
        r1.metric("Volatilità annua", f"{risk['volatility']:.2%}" if risk.get("volatility") is not None else "n.d.")
        r2.metric("Max drawdown", f"{risk['max_drawdown']:.2%}" if risk.get("max_drawdown") is not None else "n.d.")
        r3.metric("Sharpe / Sortino",
                  " / ".join(f"{risk[k]:.2f}" if risk.get(k) is not None else "n.d."
                             for k in ("sharpe", "sortino")))

        c1, c2, c3 = st.columns(3)
        c1.metric("Valore finale lordo", f"€ {summary['final_gross']:,.2f}", f"CAGR {summary['cagr_gross']:.2%}")
        c2.metric("Valore finale broker", f"€ {summary['final_broker']:,.2f}", f"CAGR {summary['cagr_broker']:.2%}")
        c3.metric("Valore finale netto", f"€ {summary['final_net']:,.2f}", f"CAGR {summary['cagr_net']:.2%}")

        chart_cols = [c for c in ["GrossPortfolioValue", "BrokerPortfolioValue", "Net"] if c in df_log.columns]
        if chart_cols:
            st.line_chart(df_log[chart_cols])

        st.download_button(
            "Scarica risultati Excel",
            data=to_excel_bytes(df_log, df_delta),
            file_name="portfolio_backtest.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        with st.expander("Anteprima risultati"):
            st.dataframe(df_log.tail(100), use_container_width=True)

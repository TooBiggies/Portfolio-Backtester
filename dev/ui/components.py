from __future__ import annotations

"""
ui/components.py

Responsabilità:
- Renderizzare i componenti Streamlit principali dell'app:
  1) Input globali (capitale, date)
  2) Portfolio builder (lista righe ticker/% con add/reset/remove)
  3) Validazioni UI (somma = 100%, ticker validi, righe vuote)
  4) Visualizzazione risultati (KPI, grafico Altair, tabelle, download)

Note architetturali:
- Questo modulo *non* esegue il backtest: quello è in services/backtest_service.py.
- Qui gestiamo solo UI + conversione "percentuali" -> "pesi (0-1)" richiesta dal service.

TODO (sviluppo futuro):
- Multi-portafoglio: trasformare `portfolio_rows` (singolo) in una lista di portafogli,
  ciascuno con un suo set di righe, e poi orchestrare la comparazione.
"""

from typing import Any, Dict, List

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from services.backtest_service import BacktestResults


# Universo ticker disponibile in UI.
# Nota: DEVE essere coerente con l'ordine atteso dall'engine di backtest (`portfolio_evo`).
DEFAULT_TICKERS = ["VT", "SPY", "VXUS", "GLD", "CASH", "SHY", "IEF", "TLT", "ZROZ", "KMLM", "DBMF"]

# Allocazioni predefinite (preset) selezionabili dalla UI.
# Formato: lista di righe {"ticker": ..., "pct": ...} dove pct è 0-100.
PRESETS: Dict[str, List[Dict[str, float]]] = {
    "Custom": [],
    "Total Stock Market": [{"ticker": "VT", "pct": 100.0}],
    "60/40": [{"ticker": "VT", "pct": 60.0}, {"ticker": "ZROZ", "pct": 40.0}],
    "Permanent Portfolio": [
        {"ticker": "SPY", "pct": 25.0},
        {"ticker": "TLT", "pct": 25.0},
        {"ticker": "GLD", "pct": 25.0},
        {"ticker": "CASH", "pct": 25.0},
    ],
}

# Placeholder per input ticker (free text)
TICKER_EMPTY_LABEL = "— Inizia a digitare il ticker che vuoi aggiungere al portafoglio —"


# -----------------------------
# Session state helpers
# -----------------------------

def _default_rows_empty() -> List[Dict[str, float]]:
    """
    Stato iniziale del builder: una singola riga vuota.

    Perché:
    - UX: l'utente capisce subito dove inserire il primo ticker.
    - Tech: evitiamo casi edge con lista vuota.
    """
    return [{"id": 1, "ticker": "", "pct": 0.0}]


def _sanitize_portfolio_rows(value: Any, ticker_universe: List[str]) -> List[Dict[str, float]]:
    """
    Normalizza/migra `portfolio_rows` verso il formato atteso:

        List[{"id": int, "ticker": str, "pct": float}]

    Perché:
    - Streamlit mantiene `st.session_state` tra rerun.
    - Durante refactor, la struttura può cambiare e generare errori (es. string indices).

    Se non riconosce il formato, resetta a una riga vuota.

    Args:
        value: stato esistente preso da st.session_state.get("portfolio_rows").
        ticker_universe: non usato direttamente qui, ma utile se in futuro vuoi migrare
                         validando/normalizzando i ticker.

    Returns:
        Lista di dict in formato standard.
    """
    try:
        if value is None:
            return _default_rows_empty()

        # Caso "corretto": list di dict
        if isinstance(value, list) and all(isinstance(x, dict) for x in value):
            rows: List[Dict[str, float]] = []
            for x in value:
                t = str(x.get("ticker", "")).strip()

                try:
                    pct = float(x.get("pct", 0.0))
                except Exception:
                    pct = 0.0

                try:
                    rid = int(x.get("id", 0))
                except Exception:
                    rid = 0

                rows.append({"id": rid, "ticker": t, "pct": float(pct)})

            # Sistema id mancanti/duplicati per evitare collisioni nelle keys Streamlit.
            used = set()
            next_id = 1
            for r in rows:
                if r["id"] <= 0 or r["id"] in used:
                    while next_id in used:
                        next_id += 1
                    r["id"] = next_id
                used.add(r["id"])

            return rows if rows else _default_rows_empty()

        # Caso legacy: dict ticker->pct (es. {"VT": 60, "ZROZ": 40})
        if isinstance(value, dict):
            rows = []
            rid = 1
            for k, v in value.items():
                t = str(k).strip()
                try:
                    pct = float(v)
                except Exception:
                    pct = 0.0
                rows.append({"id": rid, "ticker": t, "pct": pct})
                rid += 1
            return rows if rows else _default_rows_empty()

        # Qualunque altro formato non gestito -> reset
        return _default_rows_empty()
    except Exception:
        # Fallback "safe": mai far crashare la UI per stato corrotto
        return _default_rows_empty()


def _init_portfolio_state(ticker_universe: List[str]) -> None:
    """
    Inizializza le chiavi Streamlit necessarie al builder.

    Chiavi:
    - ticker_universe: lista ticker validi
    - portfolio_rows: righe del portafoglio
    - portfolio_next_id: contatore id (evita collisioni keys)
    - portfolio_preset: preset selezionato
    """
    st.session_state["ticker_universe"] = ticker_universe

    # Migrazione/sanitize per evitare errori quando cambiano le strutture dati nel tempo.
    st.session_state["portfolio_rows"] = _sanitize_portfolio_rows(
        st.session_state.get("portfolio_rows"),
        ticker_universe,
    )

    if "portfolio_next_id" not in st.session_state:
        max_id = max((r["id"] for r in st.session_state["portfolio_rows"]), default=0)
        st.session_state["portfolio_next_id"] = max_id + 1

    if "portfolio_preset" not in st.session_state:
        st.session_state["portfolio_preset"] = "Custom"


def _set_rows(rows: List[Dict[str, float]]) -> None:
    """
    Imposta `portfolio_rows` a partire da un preset.

    Nota:
    - Assegniamo nuovi id progressivi per mantenere le keys Streamlit stabili e univoche.
    """
    st.session_state["portfolio_rows"] = []
    for r in rows:
        st.session_state["portfolio_rows"].append(
            {
                "id": int(st.session_state["portfolio_next_id"]),
                "ticker": str(r.get("ticker", "")).strip(),
                "pct": float(r.get("pct", 0.0)),
            }
        )
        st.session_state["portfolio_next_id"] += 1


def _add_row_empty() -> None:
    """Aggiunge una nuova riga vuota al builder."""
    st.session_state["portfolio_rows"].append(
        {"id": int(st.session_state["portfolio_next_id"]), "ticker": "", "pct": 0.0}
    )
    st.session_state["portfolio_next_id"] += 1


def _remove_row(row_id: int) -> None:
    """
    Rimuove una riga dal builder.
    Manteniamo almeno una riga vuota per evitare UI "vuota".
    """
    st.session_state["portfolio_rows"] = [r for r in st.session_state["portfolio_rows"] if r["id"] != row_id]
    if len(st.session_state["portfolio_rows"]) == 0:
        _add_row_empty()


# -----------------------------
# Portfolio conversion & validation helpers
# -----------------------------

def _compute_weights_list(rows: List[Dict[str, float]], ticker_universe: List[str]) -> Dict[str, Any]:
    """
    Converte le righe (ticker + percentuale) in:
    - weights_dict: dict ticker->peso (0-1)
    - weights_list: lista pesi ordinata secondo ticker_universe (input per backtest)
    - total_pct: somma percentuali (0-100)
    - duplicates/invalid/empty_rows: info per validazione UI

    Scelte:
    - pct negative vengono clampate a 0.
    - ticker duplicati: li sommiamo (ma segnaliamo in UI).
    - ticker non validi: li escludiamo dal calcolo (ma segnaliamo in UI).
    """
    weights_dict: Dict[str, float] = {}
    duplicates: set[str] = set()
    invalid: set[str] = set()
    empty_rows = 0

    total_pct = 0.0
    for r in rows:
        t = str(r.get("ticker", "")).strip().upper()

        try:
            pct = float(r.get("pct", 0.0))
        except Exception:
            pct = 0.0

        pct = max(pct, 0.0)
        total_pct += pct

        # Riga vuota: non contribuisce ai pesi, ma la consideriamo per bloccare il run.
        if t == "":
            empty_rows += 1
            continue

        # Ticker non in universe: escluso dal calcolo pesi (e segnato come invalid).
        if t not in ticker_universe:
            invalid.add(t)
            continue

        # Duplicati: sommiamo, ma avvisiamo.
        if t in weights_dict:
            duplicates.add(t)

        weights_dict[t] = weights_dict.get(t, 0.0) + pct / 100.0

    # weights_list ordinata (compatibile con `portfolio_evo`)
    weights_list = [float(weights_dict.get(t, 0.0)) for t in ticker_universe]

    return {
        "weights_dict": weights_dict,
        "weights_list": weights_list,
        "weights_sum": float(np.sum(weights_list)),
        "total_pct": float(total_pct),
        "duplicates": sorted(list(duplicates)),
        "invalid_tickers": sorted(list(invalid)),
        "empty_rows": empty_rows,
    }


def _render_total_box(total_pct: float) -> None:
    """
    Renderizza un box "Total %" ad alto contrasto (OK/KO).
    Usato come feedback immediato all'utente.
    """
    ok = np.isclose(total_pct, 100.0, atol=0.5)
    bg = "#16a34a" if ok else "#dc2626"
    sub = "OK" if ok else "Deve essere 100%"

    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-radius:14px;
            padding:16px 16px;
            border:1px solid rgba(255,255,255,0.18);
            box-shadow: 0 8px 24px rgba(0,0,0,0.25);
        ">
            <div style="font-size:13px; color:rgba(255,255,255,0.85); letter-spacing:0.2px;">
                Total
            </div>
            <div style="display:flex; align-items:baseline; gap:10px; margin-top:4px;">
                <div style="font-size:40px; font-weight:800; color:white; line-height:1;">
                    {total_pct:.0f}
                </div>
                <div style="font-size:22px; font-weight:700; color:rgba(255,255,255,0.92);">
                    %
                </div>
            </div>
            <div style="margin-top:6px; font-size:12px; color:rgba(255,255,255,0.85);">
                {sub}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# UI entry points
# -----------------------------

def render_main_inputs(imported_dataframe: pd.DataFrame) -> Dict[str, Any]:
    """
    Renderizza la UI principale (parametri + builder portafoglio).
    Ritorna un dict con tutti gli input già normalizzati e pronti per essere validati/consumati.

    Nota:
    - Questa funzione NON lancia il backtest: ritorna solo inputs e flag `run_clicked`.
    - L'output viene usato da app.py per orchestrare:
        inputs -> validate -> run_backtest -> render_results
    """
    # Debug-only: utile durante refactor perché Streamlit conserva session_state.
    # In produzione si può nascondere dietro una flag (es. st.secrets["debug"]).
    with st.expander("Debug"):
        if st.button("Reset UI state"):
            for k in list(st.session_state.keys()):
                # includiamo sia il prefisso "portfolio_" sia le keys dinamiche
                if k.startswith(("ticker_", "pct_", "portfolio_")):
                    st.session_state.pop(k, None)
            st.rerun()

    # Range date disponibile nel dataset
    min_date = imported_dataframe["Date"].min().date()
    max_date = imported_dataframe["Date"].max().date()

    ticker_universe = DEFAULT_TICKERS
    _init_portfolio_state(ticker_universe)

    # --- Parametri globali simulazione ---
    st.subheader("Parametri simulazione")
    p1, p2, p3 = st.columns([1, 1, 1])

    with p1:
        initial_balance = st.number_input(
            "Capitale iniziale",
            min_value=1000,
            max_value=1_000_000,
            value=10_000,
            step=1000,
        )
    with p2:
        start_date = st.date_input(
            "Data iniziale",
            value=min(max_date, pd.to_datetime("2025-01-01").date()),
            min_value=min_date,
            max_value=max_date,
        )
    with p3:
        end_date = st.date_input(
            "Data finale",
            value=min(max_date, pd.to_datetime("2025-09-01").date()),
            min_value=min_date,
            max_value=max_date,
        )

    st.divider()
    st.subheader("Portafoglio")

    # Header: "Ticker" sopra +/X, e "Allocation" sopra preset.
    # (h3 è vuoto: lascia spazio e mantiene layout allineato.)
    h1, h2, h3 = st.columns([1.6, 4.2, 1.2])

    with h1:
        st.markdown("**Ticker**")
        b1, b2 = st.columns([1, 1])
        add_clicked = b1.button("➕", use_container_width=True)
        reset_clicked = b2.button("❌", use_container_width=True)

    with h2:
        st.markdown("**Allocation**")
        preset = st.selectbox(
            label="Allocation",
            options=list(PRESETS.keys()),
            index=list(PRESETS.keys()).index(st.session_state["portfolio_preset"]),
            label_visibility="collapsed",
        )

    with h3:
        st.markdown("&nbsp;", unsafe_allow_html=True)

    # Applica preset: ogni preset sovrascrive le righe correnti.
    if preset != st.session_state["portfolio_preset"]:
        st.session_state["portfolio_preset"] = preset
        if preset != "Custom":
            _set_rows(PRESETS[preset])
        else:
            # Custom: riparti da una riga vuota
            st.session_state["portfolio_rows"] = _default_rows_empty()
        st.rerun()

    # Reset: ripristina portafoglio vuoto (singola riga).
    if reset_clicked:
        st.session_state["portfolio_rows"] = _default_rows_empty()
        st.session_state["portfolio_preset"] = "Custom"
        st.rerun()

    # Add row: aggiunge una nuova riga vuota.
    if add_clicked:
        _add_row_empty()
        st.session_state["portfolio_preset"] = "Custom"
        st.rerun()

    # Layout: righe a sinistra + total box a destra
    left, right = st.columns([3.2, 1.0])

    with left:
        rows = st.session_state["portfolio_rows"]
        for r in rows:
            row_id = int(r["id"])
            col_t, col_w, col_x = st.columns([2.2, 1.2, 0.5])

            # Ticker input (free-text). Convertiamo a upper per standardizzare.
            with col_t:
                # Selectbox con ricerca: clicca e inizia a digitare per filtrare
                t_key = f"ticker_sel_{row_id}"

                options = [TICKER_EMPTY_LABEL] + ticker_universe

                # Valore corrente della riga (se non c'è o non è valido -> placeholder)
                current = str(r.get("ticker", "") or "").strip().upper()
                if current not in ticker_universe:
                    current = TICKER_EMPTY_LABEL

                # Se lo stato non esiste ancora, inizializzalo coerente
                if t_key not in st.session_state:
                    st.session_state[t_key] = current

                selected = st.selectbox(
                    label="Ticker",
                    options=options,
                    index=options.index(st.session_state[t_key]) if st.session_state[t_key] in options else 0,
                    key=t_key,
                    label_visibility="collapsed",
                )

                # Mappa placeholder -> ticker vuoto
                r["ticker"] = "" if selected == TICKER_EMPTY_LABEL else selected

            # Percentuale allocazione
            with col_w:
                p_key = f"pct_{row_id}"
                if p_key not in st.session_state:
                    st.session_state[p_key] = float(r.get("pct", 0.0) or 0.0)

                pct = st.number_input(
                    label="%",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(st.session_state[p_key]),
                    step=1.0,
                    key=p_key,
                    label_visibility="collapsed",
                )
                r["pct"] = float(pct)

            # Remove row
            with col_x:
                remove = st.button("−", key=f"remove_{row_id}", use_container_width=True)
                if remove:
                    _remove_row(row_id)
                    st.session_state["portfolio_preset"] = "Custom"
                    st.rerun()

    # Calcolo pesi e totale per feedback/validazione
    conv = _compute_weights_list(st.session_state["portfolio_rows"], ticker_universe)

    with right:
        _render_total_box(conv["total_pct"])

    st.divider()
    run_clicked = st.button("Esegui Backtest", type="primary")

    # Output normalizzato: app.py userà questo dict.
    return {
        "initial_balance": int(initial_balance),
        "start_date": pd.to_datetime(start_date),
        "end_date": pd.to_datetime(end_date),
        "portfolio_rows": st.session_state["portfolio_rows"],
        "ticker_universe": ticker_universe,
        **conv,
        "run_clicked": run_clicked,
        "min_date": min_date,
        "max_date": max_date,
    }


def render_validation_messages(inputs: Dict[str, Any]) -> bool:
    """
    Mostra messaggi di errore/warning e decide se la simulazione può partire.

    Regole attuali:
    - start_date <= end_date
    - nessun ticker invalido
    - nessuna riga ticker vuota (blocca solo quando l'utente preme Run)
    - total_pct ≈ 100 (blocca solo quando l'utente preme Run)
    - weights_sum > 0
    """
    ok = True

    if inputs["start_date"] > inputs["end_date"]:
        st.error("La data iniziale non può essere successiva alla data finale.")
        ok = False

    # Duplicati: non blocchiamo (li sommiamo), ma segnaliamo.
    if inputs["duplicates"]:
        st.info(f"Ticker duplicati: {', '.join(inputs['duplicates'])} (i pesi vengono sommati).")

    # Ticker invalidi: blocchiamo sempre perché l'engine non saprebbe come gestirli.
    if inputs["invalid_tickers"]:
        st.error(f"Ticker non validi: {', '.join(inputs['invalid_tickers'])}. Usa solo ticker disponibili.")
        ok = False

    # Righe vuote: warning sempre, blocco solo quando run_clicked
    if inputs["empty_rows"] > 0:
        st.warning("Ci sono righe con ticker vuoto. Compila o rimuovi le righe.")
        if inputs["run_clicked"]:
            ok = False

    # Somma percentuali: warning sempre, blocco solo quando run_clicked
    if not np.isclose(inputs["total_pct"], 100.0, atol=0.5):
        st.warning("La somma delle percentuali deve essere 100%.")
        if inputs["run_clicked"]:
            ok = False

    # weights_sum: check tecnico. Se =0 non ha senso lanciare.
    if inputs["weights_sum"] <= 0:
        st.error("Somma pesi = 0: imposta almeno una percentuale > 0.")
        ok = False

    return ok


def render_results(results: BacktestResults) -> None:
    """
    Renderizza la sezione risultati di un backtest:
    - KPI principali
    - Grafico Altair del valore del portafoglio (NetTotValue)
    - Tabelle + download excel

    Nota:
    - Il grafico è volutamente costruito *qui* a partire da df_log:
      BacktestResults rimane un container dati neutro.
    """
    st.success("Backtest completato ✅")

    # KPI header
    c1, c2, c3 = st.columns(3)
    c1.metric("Orizzonte Temporale", results.metrics["Orizzonte"])
    c2.metric("Anni", str(results.metrics["Anni in simulazione"]))
    c3.metric("CAGR", f"{results.metrics['CAGR (%)']:.2f}%" if results.metrics["CAGR (%)"] is not None else "—")

    c4, c5, c6 = st.columns(3)
    c4.metric("Total Return", f"{results.metrics['Total compound return (%)']:.2f}%")
    c5.metric("Capitale iniziale", f"{results.metrics['Capitale iniziale']:.0f}")
    c6.metric("Capitale finale", f"{results.metrics['Capitale finale']:.2f}")

    st.divider()

    # --- Grafico (NetTotValue) ---
    st.subheader("Valore portafoglio (NetTotValue)")

    # Preparazione df per Altair
    plot_df = results.df_log[["NetTotValue"]].copy()
    plot_df.index.name = "Date"
    plot_df = plot_df.reset_index().rename(columns={"NetTotValue": "Value"})
    plot_df = plot_df.dropna(subset=["Value"])

    # Nota: scala log richiede Value > 0. Se ci sono zeri/negativi, Altair fallisce.
    plot_df = plot_df[plot_df["Value"] > 0]

    chart = (
        alt.Chart(plot_df)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Value:Q", title="NetTotValue").scale(zero=False, type="log"),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Value:Q", title="NetTotValue", format=",.2f"),
            ],
        )
        .properties(height=400)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)

    # --- Tabelle + Download ---
    tabs = st.tabs(["Log (df_log)", "Delta (df_log_delta)", "Download"])
    with tabs[0]:
        st.dataframe(results.df_log, use_container_width=True)
    with tabs[1]:
        st.dataframe(results.df_log_delta, use_container_width=True)
    with tabs[2]:
        st.download_button(
            "⬇️ Scarica output_ptf.xlsx",
            data=results.excel_ptf_bytes,
            file_name="output_ptf.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "⬇️ Scarica output_ptf_delta.xlsx",
            data=results.excel_delta_bytes,
            file_name="output_ptf_delta.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
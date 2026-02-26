"""
app.py

Entrypoint Streamlit dell'app "Portfolio Backtester".

Responsabilità:
- Setup della pagina Streamlit (titolo/layout).
- Caricare i dati (via data_service, con caching).
- Renderizzare UI input (via ui/components).
- Validare input (via ui/components).
- Eseguire il backtest (via backtest_service) quando l'utente preme "Run".
- Renderizzare risultati (via ui/components).

Note architetturali:
- Qui non ci sono dettagli di business logic: orchestration-only.
- La UI è delegata a ui/components.py
- Il backtest è delegato a services/backtest_service.py

TODO (futuro):
- Comparazione multi-portafoglio:
  - sostituire `run_backtest` con un orchestratore `run_comparison`
  - salvare/gestire più portafogli in session_state e visualizzare KPI + grafico multi-line
"""

from __future__ import annotations

import streamlit as st

from services.backtest_service import run_backtest
from services.data_service import load_timeseries
from ui.components import (
    render_main_inputs,
    render_results,
    render_validation_messages,
)

# Config base della pagina.
# layout="wide" perché il builder portafoglio + box total + chart beneficiano di spazio orizzontale.
st.set_page_config(page_title="Portfolio Backtester", layout="wide")


def main() -> None:
    """Main Streamlit function: orchestration UI -> validate -> run -> render."""
    st.title("📈 Portfolio Backtester")

    # Caricamento storico:
    # - La funzione è cached (st.cache_data), quindi non viene riletta ad ogni rerun.
    # - cutoff_start/cutoff_end definiscono il range massimo disponibile per la UI.
    imported_dataframe = load_timeseries(
        csv_path="./Timeseries.csv",
        cutoff_start="2000-01-03",
        cutoff_end="2025-09-04",
        sep=";",
    )

    # Render UI e raccolta input (include "run_clicked").
    # Nota: questa funzione gestisce anche lo stato del portfolio builder (session_state).
    inputs = render_main_inputs(imported_dataframe)

    # Mostra messaggi e determina se possiamo lanciare il backtest.
    # Nota: la funzione decide se bloccare solo quando run_clicked=True.
    ok_to_run = render_validation_messages(inputs)

    # Esecuzione on-demand: solo quando l'utente preme il bottone.
    if inputs["run_clicked"]:
        if not ok_to_run:
            # Interrompe l'esecuzione del turno corrente (UI resta visibile).
            st.stop()

        # Spinner: feedback UI durante operazioni potenzialmente lente
        with st.spinner("Esecuzione backtest in corso..."):
            results = run_backtest(
                imported_dataframe=imported_dataframe,
                initial_balance=inputs["initial_balance"],
                start_date=inputs["start_date"],
                end_date=inputs["end_date"],
                initial_w=inputs["weights_list"],
            )

        # Visualizza KPI, grafico, tabelle e download
        render_results(results)


if __name__ == "__main__":
    main()
from __future__ import annotations

"""
services/data_service.py

Responsabilità:
- Caricare lo storico prezzi/serie temporali dal CSV (Timeseries.csv).
- Normalizzare la colonna Date in datetime.
- Applicare un filtro temporale (cutoff_start / cutoff_end).
- Esporre una funzione cached (Streamlit) per evitare reload ad ogni rerun.

Nota:
- Questo service NON conosce nulla della UI o del backtest. Fornisce solo dati puliti.
"""

import pandas as pd
import streamlit as st


@st.cache_data(show_spinner=False)
def load_timeseries(
    csv_path: str,
    cutoff_start: str,
    cutoff_end: str,
    sep: str = ";",
) -> pd.DataFrame:
    """
    Carica uno storico da CSV e applica filtri sulla colonna 'Date'.

    Args:
        csv_path: percorso al CSV (es. "./Timeseries.csv").
        cutoff_start: data minima inclusiva (es. "2000-01-03").
        cutoff_end: data massima inclusiva (es. "2025-09-04").
        sep: separatore CSV (default ";").

    Returns:
        DataFrame con colonna 'Date' convertita a datetime e filtrata nel range richiesto.

    Raises:
        ValueError: se la colonna 'Date' non è presente nel CSV.

    Note su caching (Streamlit):
        - `st.cache_data` evita di rileggere il CSV ad ogni rerun.
        - La cache viene invalidata se cambiano:
          1) il contenuto del file (dipende dall'hash calcolato internamente),
          2) i parametri passati alla funzione.
    """
    # Lettura raw
    df = pd.read_csv(csv_path, sep=sep)

    # Check minimo: ci serve la colonna Date per filtrare
    if "Date" not in df.columns:
        raise ValueError("Colonna 'Date' non trovata nel CSV.")

    # Parsing Date: dayfirst=True perché nel dataset la data è in formato gg/mm/aaaa
    # errors="coerce" trasforma le date non parsabili in NaT, che poi droppiamo.
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"]).copy()

    # Cutoff temporale
    # Nota: pd.to_datetime accetta stringhe ISO (YYYY-MM-DD), consigliato per evitare ambiguità.
    start = pd.to_datetime(cutoff_start)
    end = pd.to_datetime(cutoff_end)

    # Filtro inclusivo su start/end
    df = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()

    # Reset index per coerenza (utile per debug/export e per evitare indici “bucati”)
    df = df.reset_index(drop=True)
    return df
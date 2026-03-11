from __future__ import annotations

"""
services/backtest_service.py

Responsabilità:
- Eseguire UN singolo backtest di portafoglio usando la classe `portfolio_evo`.
- Restituire risultati strutturati (log temporale + metriche + file Excel in-memory)
  così la UI Streamlit può:
  - mostrare KPI e tabelle
  - renderizzare grafici (Altair) partendo dai dataframe
  - offrire download .xlsx senza scrivere su disco

Nota sul futuro:
- Questo modulo deve rimanere "single-portfolio".
  La comparazione multi-portafoglio verrà implementata in un service separato
  che chiamerà `run_backtest()` N volte e aggrega KPI + curve.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from classes import portfolio_evo


@dataclass(frozen=True)
class BacktestResults:
    """
    Risultati di un singolo backtest.

    Attributi:
        df_log:
            DataFrame indicizzato per data (DateTimeIndex) con metriche e serie temporali
            di portafoglio (Return, TotValue, NetTotValue, etc.).
        df_log_delta:
            DataFrame indicizzato per data con delta notional * prezzo (per asset).
        metrics:
            Dizionario con KPI principali (CAGR, orizzonte, capitale finale, ...).
        excel_ptf_bytes / excel_delta_bytes:
            Contenuto dei due Excel (in-memory) per `st.download_button`.
    """
    df_log: pd.DataFrame
    df_log_delta: pd.DataFrame
    metrics: Dict[str, Any]
    excel_ptf_bytes: bytes
    excel_delta_bytes: bytes


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Serializza un DataFrame in formato Excel (.xlsx) in-memory.

    Perché:
    - Streamlit: download diretto senza file temporanei su disco.
    - Separazione dei concern: la UI decide se/come offrire il download.

    Nota:
    - Usa openpyxl come engine (deve essere presente nei requirements).
    """
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=True)
    return bio.getvalue()


def run_backtest(
    imported_dataframe: pd.DataFrame,
    initial_balance: int,
    start_date,
    end_date,
    initial_w: List[float],
) -> BacktestResults:
    """
    Esegue il backtest per un singolo portafoglio.

    Args:
        imported_dataframe: storico prezzi/serie temporali già caricato e filtrato.
        initial_balance: capitale iniziale (es. 10000).
        start_date: data inizio simulazione (datetime-like).
        end_date: data fine simulazione (datetime-like).
        initial_w: lista di pesi (0-1) ordinata secondo l'universo degli asset
                   atteso da `portfolio_evo`.

    Returns:
        BacktestResults con df_log, df_log_delta, KPI e bytes Excel.

    Raises:
        ValueError: se i pesi non sommano a 1 (entro tolleranza).
    """
    # Validazione pesi: in questa pipeline i pesi devono sommare a 1.
    # (La UI può bloccare prima, ma qui facciamo un check "di sicurezza".)
    w_sum = float(np.sum(initial_w))
    if not np.isclose(w_sum, 1.0, atol=1e-6):
        raise ValueError(f"L'allocazione non somma a 1 (somma={w_sum:.6f}).")

    # Istanziazione del motore di backtest.
    # Nota: i parametri sono "hard-coded" perché attualmente sono assunti globali.
    # In futuro possono diventare parametri UI o config.
    ptf = portfolio_evo(
        initial_balance=initial_balance,
        transac_cost_rate=0.0029,  # 0.19% commissioni + 0.1% spread
        exp_rate=0.002,            # 0.2% imposta di bollo + 0% tracking error
        tax_rate=0.26,             # 26% (assunzione conservativa)
        rebalance_threshold=0.1,
        initial_w=initial_w,
        imported_dataframe=imported_dataframe,
        start_date=start_date,
        end_date=end_date,
        stock_price_normalization=True,  # Nota: influenza solo la normalizzazione dei prezzi interni
    )

    # Log temporali: uno "main" e uno per il delta notional.
    df_log = pd.DataFrame(index=ptf.date)
    df_log_delta = pd.DataFrame(index=ptf.date)

    # Loop giornaliero: aggiorna stato portafoglio e salva metriche nel log.
    # Nota: `ptf.StockPrice.index` è l'indice delle righe della serie prezzi.
    for i in ptf.StockPrice.index:
        # Reset giornaliero dei contatori che vengono calcolati "per step".
        ptf.reset_tax_transaccost()
        ptf.reset_delta_notional()

        # Prezzi al tempo i per ogni asset
        stock_price = ptf.StockPrice.loc[i, :]

        # Aggiorna valore asset/weight e verifica necessità rebalance.
        ptf.update_AssetValue_weight(stock_price)
        if ptf.check_rebalance():
            ptf.update_notional_tax_transaccost(stock_price)

        # Aggiorna ritorni e valori totali (lordo e netto)
        ptf.update_Return(stock_price)
        ptf.update_TotValue(stock_price)
        ptf.update_NetTotValue(stock_price)

        # Persist nel log principale
        dt = ptf.date[i]
        df_log.loc[dt, "Return"] = ptf.PercReturn
        df_log.loc[dt, "Compound Return"] = ptf.CompoundReturn
        df_log.loc[dt, "TotValue"] = ptf.TotValue
        df_log.loc[dt, "NetTotValue"] = ptf.NetTotValue  # scelta 2: valore NON normalizzato, netto
        df_log.loc[dt, "Taxes"] = ptf.tax
        df_log.loc[dt, "TransacCost"] = ptf.TransactionalCost

        # Serie per singolo asset (colonne = nomi indice/asset)
        # `ptf.IndexName` è atteso come lista/iterabile di nomi colonna.
        df_log.loc[dt, ptf.IndexName] = ptf.AssetValue

        # Persist nel log delta
        df_log_delta.loc[dt, ptf.IndexName] = ptf.delta_notional * stock_price

    # KPI principali
    start_dt = min(ptf.date)
    end_dt = max(ptf.date)
    years = round(((end_dt - start_dt).days / 365.25), 2)

    # CAGR basato su CompoundReturn (tipicamente >= 0).
    # Nota: se years == 0 (range troppo corto), evitiamo divisioni.
    cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100 if years > 0 else np.nan

    metrics: Dict[str, Any] = {
        "Orizzonte": f"{start_dt.date()} / {end_dt.date()}",
        "Anni in simulazione": years,
        "CAGR (%)": float(cagr) if cagr == cagr else None,  # NaN-safe
        "Total compound return (%)": float(ptf.CompoundReturn * 100),
        "Capitale iniziale": float(ptf.StartValue),
        "Capitale finale": float(ptf.TotValue),
        # Nota: se vuoi coerenza con NetTotValue, potresti aggiungere anche:
        # "Capitale finale (netto)": float(ptf.NetTotValue)
    }

    # Excel download (in-memory)
    excel_ptf_bytes = _to_excel_bytes(df_log)
    excel_delta_bytes = _to_excel_bytes(df_log_delta)

    return BacktestResults(
        df_log=df_log,
        df_log_delta=df_log_delta,
        metrics=metrics,
        excel_ptf_bytes=excel_ptf_bytes,
        excel_delta_bytes=excel_delta_bytes,
    )
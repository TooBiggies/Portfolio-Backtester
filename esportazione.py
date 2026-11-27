"""Prepara il file Excel scaricabile dall'app.

Due cose, entrambe necessarie.

**1. Le colonne che rivelano i prezzi non escono.** Il log interno contiene una colonna
per asset e per giorno: `Price_*` (il prezzo), `PMC_*` (il prezzo medio di carico) e
`Broker_*`/`Gross_*`/`Net_*` (il controvalore). Le ultime sembrano innocue ma non lo
sono: fra due ribilanciamenti le quote restano ferme, quindi il rapporto fra due valori
consecutivi **è** il rapporto fra due prezzi. Con un solo prezzo noto si ricostruisce
l'intera serie giornaliera — esattamente ciò che il permesso di testfol.io vieta di
ridistribuire (vedi PERMISSION.md).

**2. Restano solo le finestre di ribilanciamento.** Dell'intera storia servono poche
righe: quelle attorno ai giorni in cui il portafoglio viene riequilibrato, più la prima
e l'ultima. Una manciata di righe sparse non permette di ricostruire nulla, e il file
passa da decine di migliaia di righe a poche decine.

I totali di portafoglio (`BrokerPortfolioValue`, `Net`, `GrossPortfolioValue`) restano:
sono il risultato della simulazione, non la serie di mercato.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

# Colonne per asset che contengono, direttamente o indirettamente, il prezzo.
PREFISSI_RISERVATI = ("Price_", "PMC_", "Broker_", "Gross_", "Net_", "HoldingCost_")
# Quante sedute prima e dopo un ribilanciamento si tengono.
GIORNI_INTORNO = 2


def colonne_esportabili(df_log: pd.DataFrame) -> list[str]:
    """Le colonne del log che possono uscire senza rivelare i prezzi."""
    return [c for c in df_log.columns if not c.startswith(PREFISSI_RISERVATI)]


def date_ribilanciamento(df_delta: pd.DataFrame) -> list:
    """Le date in cui almeno un asset è stato comprato o venduto."""
    if df_delta is None or df_delta.empty:
        return []
    movimento = df_delta.fillna(0.0).abs().sum(axis=1)
    return [data for data, totale in movimento.items() if totale > 0]


def righe_da_esportare(df_log: pd.DataFrame, df_delta: pd.DataFrame) -> pd.DataFrame:
    """Le righe del log da tenere: intorno ai ribilanciamenti, più la prima e l'ultima."""
    if df_log.empty:
        return df_log

    posizioni = {0, len(df_log) - 1}
    indice = list(df_log.index)
    posizione_di = {data: i for i, data in enumerate(indice)}

    for data in date_ribilanciamento(df_delta):
        centro = posizione_di.get(data)
        if centro is None:
            continue
        inizio = max(0, centro - GIORNI_INTORNO)
        fine = min(len(indice), centro + GIORNI_INTORNO + 1)
        posizioni.update(range(inizio, fine))

    return df_log.iloc[sorted(posizioni)]


def to_excel_bytes(df_log: pd.DataFrame, df_delta: pd.DataFrame) -> bytes:
    """Excel con i risultati: finestre di ribilanciamento, senza le serie di prezzo."""
    colonne = colonne_esportabili(df_log)
    righe = righe_da_esportare(df_log[colonne], df_delta)

    delta = df_delta.copy()
    if not delta.empty:
        movimento = delta.fillna(0.0).abs().sum(axis=1)
        delta = delta[movimento > 0]

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        righe.to_excel(writer, sheet_name="Portfolio")
        delta.to_excel(writer, sheet_name="Rebalancing")
    return buffer.getvalue()

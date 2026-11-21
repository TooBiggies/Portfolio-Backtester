"""Conversione dei prezzi in euro o lire e deflazione per l'inflazione italiana.

Le simulazioni del dataset sono in dollari. Questa modulo permette di vederle nella
valuta in cui un risparmiatore italiano le ha vissute, e di togliere l'effetto
dell'inflazione.

Il metodo: si convertono **i prezzi**, non i valori finali. La differenza conta. Se si
convertisse il risultato alla fine, il cambio entrerebbe una volta sola e non toccherebbe
né i ribilanciamenti né le imposte; convertendo i prezzi, il portafoglio vive davvero in
euro, i ribilanciamenti scattano sugli scostamenti in euro e le plusvalenze tassate sono
quelle in euro. È la stessa scelta che farebbe un investitore che compra uno strumento
denominato in euro.

Il cambio prima del 1999 è ricostruito dalla lira (vedi ``dati/genera_cambi.py``): è la
convenzione dell'«euro sintetico», e ha una risoluzione mensile, non giornaliera.

Le serie e la loro provenienza sono documentate in ``dati/genera_cambi.py``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

VALUTE = ("USD", "EUR", "ITL")
ETICHETTE = {"USD": "dollari", "EUR": "euro", "ITL": "lire"}
SIMBOLI = {"USD": "$", "EUR": "€", "ITL": "₤"}
LIRA_PER_EURO = 1936.27
PERCORSO_PREDEFINITO = Path(__file__).resolve().parent / "dati" / "cambi_inflazione.csv"


def carica_serie(percorso=None) -> pd.DataFrame:
    """Cambio dollari per euro e indice dei prezzi italiani, per giorno."""
    percorso = Path(percorso) if percorso else PERCORSO_PREDEFINITO
    if not percorso.exists():
        raise ValueError(
            f"Serie di cambio e inflazione assenti ({percorso}). "
            "Si generano con: python dati/genera_cambi.py")
    tabella = pd.read_csv(percorso, sep=";", encoding="utf-8-sig")
    tabella["Date"] = pd.to_datetime(tabella["Date"], dayfirst=True, errors="coerce")
    tabella = tabella.dropna(subset=["Date"]).set_index("Date").sort_index()
    return tabella[["EURUSD", "CPI_IT"]].astype(float)


def fattore_cambio(valuta: str, date, serie: pd.DataFrame) -> pd.Series:
    """Quanto vale, nella valuta scelta, un dollaro in ciascuna data.

    ``EURUSD`` è espresso in dollari per euro: per passare da dollari a euro si divide.
    Le lire si ottengono dagli euro con il tasso irrevocabile di conversione.
    """
    if valuta == "USD":
        return pd.Series(1.0, index=pd.DatetimeIndex(date))
    cambio = serie["EURUSD"].reindex(pd.DatetimeIndex(date), method="ffill")
    if cambio.isna().any():
        mancanti = cambio[cambio.isna()].index
        raise ValueError(
            f"Il cambio non copre la finestra simulata: {len(mancanti)} date senza valore "
            f"(la serie va dal {serie.index.min().date()} al {serie.index.max().date()}).")
    euro = 1.0 / cambio
    return euro * (LIRA_PER_EURO if valuta == "ITL" else 1.0)


def fattore_deflazione(date, serie: pd.DataFrame) -> pd.Series:
    """Riporta i valori al potere d'acquisto della prima data della finestra.

    Con questo fattore il primo giorno vale 1: la curva dice quanto vale il portafoglio
    in euro (o lire) del giorno in cui hai investito, non in quelli di oggi.
    """
    cpi = serie["CPI_IT"].reindex(pd.DatetimeIndex(date), method="ffill")
    if cpi.isna().any():
        raise ValueError(
            f"L'indice dei prezzi non copre la finestra simulata: {int(cpi.isna().sum())} date "
            f"senza valore (la serie va dal {serie.index.min().date()} al {serie.index.max().date()}).")
    return cpi.iloc[0] / cpi


def prima_data_valida(percorso=None):
    """Prima data in cui cambio e inflazione esistono entrambi.

    Il dataset dei prezzi comincia il 31/12/1969, il cambio del dollaro contro lira
    nel 1971: se si esprime il portafoglio in euro o lire, la simulazione può partire
    solo da lì. Chiedere prima non è un errore dell'utente, è un limite dei dati.
    """
    serie = carica_serie(percorso)
    return serie.index.min()


def converti_prezzi(prezzi: pd.DataFrame, valuta: str = "USD", reale: bool = False,
                    percorso=None) -> pd.DataFrame:
    """Prezzi espressi nella valuta scelta ed eventualmente al netto dell'inflazione.

    Restituisce una copia: il DataFrame in ingresso non viene toccato, perché il chiamante
    (``backtest``) lo usa anche per controllare i buchi della finestra.
    """
    if valuta not in VALUTE:
        raise ValueError(f"Valuta {valuta!r} non gestita. Ammesse: {', '.join(VALUTE)}")
    if valuta == "USD" and not reale:
        return prezzi

    serie = carica_serie(percorso)
    date = prezzi.index

    fattore = 1.0
    if valuta != "USD":
        fattore = fattore * fattore_cambio(valuta, date, serie)
    if reale:
        fattore = fattore * fattore_deflazione(date, serie)

    return prezzi.mul(fattore, axis=0)

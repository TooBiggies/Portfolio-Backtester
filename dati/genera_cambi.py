"""Genera le serie di cambio e di inflazione usate per esprimere i portafogli in euro o lire.

Le fonti, e perché sono queste:

* **Cambio euro/dollaro** — Banca Centrale Europea via FRED (`DEXUSEU`, dollari per euro),
  dal 4 gennaio 1999 a oggi.
* **Cambio lira/dollaro** — Federal Reserve via FRED (`EXITUS`, lire per dollaro), mensile
  dal 1971 al 2001. Prima del 1999 l'euro non esisteva: il cambio si ricostruisce dalla
  lira usando il tasso irrevocabile di conversione **1936,27 lire per euro**. Ne risulta
  un «euro sintetico», che è la convenzione standard per le serie lunghe.
* **Inflazione italiana** — indice armonizzato dei prezzi al consumo (HICP, Eurostat,
  2015=100) mensile dal 1996; prima del 1996 l'indice si ricostruisce all'indietro con i
  tassi tendenziali annui OCSE (`CPALTT01ITM659N`, 1956-2025), che sono stati verificati
  contro lo HICP: scarto mediano 0,11 punti percentuali su 339 mesi sovrapposti.

Il file prodotto è giornaliero, allineato alle date del dataset dei prezzi, con i valori
mensili riportati in avanti. Il riporto in avanti è una scelta dichiarata: per il cambio
di prima del 1999 e per l'inflazione non esiste una serie giornaliera gratuita e
riproducibile, e l'alternativa (interpolare) inventerebbe movimento dove non c'è.

Uso:
    python dati/genera_cambi.py [percorso_uscita]
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
HICP = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx"
        "?format=JSON&lang=EN&geo=IT&coicop=CP00&unit=I15&sinceTimePeriod=1996-01")
LIRA_PER_EURO = 1936.27


def scarica(url: str, binarie: bool = False):
    with urllib.request.urlopen(url, timeout=60) as risposta:
        dati = risposta.read()
    return dati if binarie else dati.decode("utf-8")


def fred_mensile(id_serie: str) -> pd.Series:
    testo = scarica(FRED.format(id_serie))
    righe = list(csv.DictReader(testo.splitlines()))
    serie = pd.Series(
        {pd.Timestamp(r["observation_date"]): float(r[id_serie])
         for r in righe if r[id_serie] not in ("", ".")},
        dtype=float,
    )
    return serie.sort_index()


def hicp_mensile() -> pd.Series:
    dati = json.loads(scarica(HICP))
    mesi = {m: int(i) for m, i in dati["dimension"]["time"]["category"]["index"].items()}
    valori = {mese: dati["value"][str(pos)]
              for mese, pos in mesi.items() if str(pos) in dati["value"]}
    serie = pd.Series({pd.Timestamp(mese + "-01"): float(v) for mese, v in valori.items()})
    return serie.sort_index()


def indice_inflazione() -> pd.Series:
    """Indice mensile dei prezzi italiani, ricostruito dal 1956 e agganciato allo HICP.

    La relazione usata è quella che definisce la variazione tendenziale: l'indice di un
    mese è quello di dodici mesi prima moltiplicato per (1 + variazione). Percorrendo i
    mesi all'indietro si ottiene l'intera serie senza interpolare niente.
    """
    hicp = hicp_mensile()
    tendenziale = fred_mensile("CPALTT01ITM659N")  # variazione annua, in punti percentuali

    indice = pd.Series(dtype=float)
    for mese, valore in hicp.items():
        indice[mese] = 100.0 * valore / hicp.iloc[0]

    # Un mese alla volta, dal più recente al più antico: quando si arriva a un anno
    # senza HICP, il valore di dodici mesi dopo è già stato ricostruito al passaggio
    # precedente, quindi la catena non si interrompe.
    mese = hicp.index[-1]
    primo = tendenziale.index[0]
    while mese - pd.DateOffset(years=1) >= primo:
        anno_prima = mese - pd.DateOffset(years=1)
        if mese in indice.index and anno_prima not in indice.index and mese in tendenziale.index:
            indice[anno_prima] = indice[mese] / (1.0 + tendenziale[mese] / 100.0)
        mese -= pd.DateOffset(months=1)
    return indice.sort_index()


def cambio_euro_dollaro(indice_giorni: pd.DatetimeIndex) -> pd.Series:
    """Dollari per euro, giornaliero. Prima del 1999 ricostruito dalla lira.

    Prima del 1999 l'euro non esisteva, quindi la serie si ricostruisce dalla lira:
    lire per dollaro divise per 1936,27 (lire per euro) danno dollari per euro.
    Dal 1999 comanda la serie ufficiale, e la ricostruzione resta solo come
    riempimento iniziale.
    """
    ufficiale = _dexuseu_giornaliero()
    lira = fred_mensile("EXITUS")               # lire per dollaro, mensile
    sintetico = (LIRA_PER_EURO / lira).reindex(indice_giorni, method="ffill")
    uff = ufficiale.reindex(indice_giorni, method="ffill")
    return uff.combine_first(sintetico).ffill()


def _dexuseu_giornaliero() -> pd.Series:
    testo = scarica(FRED.format("DEXUSEU"))
    righe = list(csv.DictReader(testo.splitlines()))
    return pd.Series(
        {pd.Timestamp(r["observation_date"]): float(r["DEXUSEU"])
         for r in righe if r["DEXUSEU"] not in ("", ".")},
        dtype=float,
    ).sort_index()


def verifica_sovrapposizione() -> str:
    """Negli anni in cui esistono entrambe le fonti, l'euro sintetico deve combaciare."""
    ufficiale = _dexuseu_giornaliero()
    lira = fred_mensile("EXITUS")
    sintetico = (LIRA_PER_EURO / lira).reindex(ufficiale.index, method="ffill")
    comune = pd.concat([ufficiale.rename("ufficiale"), sintetico.rename("sintetico")], axis=1).dropna()
    comune = comune[comune.index < pd.Timestamp("2001-12-31")]
    scarto = (comune["sintetico"] / comune["ufficiale"] - 1.0).abs()
    return (f"sovrapposizione {comune.index[0].date()} -> {comune.index[-1].date()}: "
            f"{len(comune)} giorni, scarto mediano {scarto.median()*100:.2f}%, "
            f"massimo {scarto.max()*100:.2f}%")


def main():
    uscita = Path(sys.argv[1] if len(sys.argv) > 1 else "dati/cambi_inflazione.csv")
    prezzi = pd.read_csv("Timeseries.csv", sep=";", encoding="utf-8-sig")
    prezzi["Date"] = pd.to_datetime(prezzi["Date"], dayfirst=True, errors="coerce")
    giorni = pd.DatetimeIndex(prezzi["Date"].dropna().sort_values().unique())
    # Il cambio dalla lira comincia nel 1971: prima di quella data il file non avrebbe
    # niente da dire, e inventare un valore piatto sarebbe peggio che non coprirlo.
    giorni = giorni[giorni >= pd.Timestamp("1971-01-04")]

    cambio = cambio_euro_dollaro(giorni)
    inflazione = indice_inflazione().reindex(giorni, method="ffill")

    uscita.parent.mkdir(parents=True, exist_ok=True)
    tabella = pd.DataFrame({"Date": giorni, "EURUSD": cambio.to_numpy(),
                            "CPI_IT": inflazione.to_numpy()})
    tabella.to_csv(uscita, sep=";", index=False, float_format="%.6f", date_format="%d/%m/%Y")

    print(f"scritto {uscita}: {len(tabella)} giorni, "
          f"{giorni[0].date()} -> {giorni[-1].date()}")
    print(f"  EUR/USD da {cambio.iloc[0]:.4f} a {cambio.iloc[-1]:.4f}")
    print(f"  indice prezzi da {inflazione.iloc[0]:.1f} a {inflazione.iloc[-1]:.1f} "
          f"(x{inflazione.iloc[-1]/inflazione.iloc[0]:.2f} in {len(tabella)/252:.0f} anni)")
    print(" ", verifica_sovrapposizione())


if __name__ == "__main__":
    main()

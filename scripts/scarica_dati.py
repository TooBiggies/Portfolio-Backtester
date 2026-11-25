"""Recupera il dataset storico usato dal simulatore.

Il file Timeseries.csv non sta in questo repository: contiene serie esportate da
testfol.io, che ne ha autorizzato l'uso per questo progetto non commerciale ma non
la ridistribuzione (vedi PERMISSION.md). Il dataset vive quindi in un repository
privato, e questo script lo porta qui al momento del bisogno.

Uso tipico
----------
    python scripts/scarica_dati.py                  # scarica dal repository privato
    python scripts/scarica_dati.py --da C:/dati/Timeseries.csv   # copia da un file locale

Il token di lettura si passa con la variabile d'ambiente PTF_DATI_TOKEN.
Se manca, lo script non inventa niente: spiega come procurarsi il file.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY = "TooBiggies/Portfolio-Backtester-dati"
PERCORSO = "Timeseries.csv"
RIF = "main"
# una serie di 49 anni in questo formato pesa oltre un megabyte: se arriva molto meno,
# il download è andato storto anche se il server ha risposto 200
DIMENSIONE_MINIMA = 200_000


def scarica(destinazione: Path, token: str, ref: str) -> None:
    """Scarica il CSV via API di GitHub, con il token di sola lettura."""
    indirizzo = (
        f"https://api.github.com/repos/{REPOSITORY}/contents/{PERCORSO}?ref={ref}"
    )
    richiesta = urllib.request.Request(
        indirizzo,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw",
            "User-Agent": "Portfolio-Backtester",
        },
    )
    try:
        with urllib.request.urlopen(richiesta, timeout=120) as risposta:
            contenuto = risposta.read()
    except urllib.error.HTTPError as errore:
        if errore.code == 404:
            sys.exit(
                f"Il dataset non è stato trovato in {REPOSITORY} ({ref}).\n"
                "Controlla di avere accesso al repository privato."
            )
        if errore.code in (401, 403):
            sys.exit(
                "Token non valido o senza permesso di lettura sul repository privato.\n"
                "Serve un fine-grained token con 'Contents: Read-only' su "
                f"{REPOSITORY}."
            )
        raise

    destinazione.write_bytes(contenuto)
    if destinazione.stat().st_size < DIMENSIONE_MINIMA:
        destinazione.unlink(missing_ok=True)
        sys.exit(
            "Il file scaricato è troppo piccolo per essere il dataset completo: "
            "download interrotto, niente è stato scritto."
        )


def copia_locale(origine: Path, destinazione: Path) -> None:
    """Copia il dataset da un file che l'utente ha già in casa."""
    if not origine.exists():
        sys.exit(f"File non trovato: {origine}")
    destinazione.write_bytes(origine.read_bytes())


def main() -> None:
    analizzatore = argparse.ArgumentParser(description=__doc__)
    analizzatore.add_argument(
        "--destinazione",
        default="Timeseries.csv",
        help="dove scrivere il dataset (predefinito: radice del repository)",
    )
    analizzatore.add_argument(
        "--da",
        default=None,
        help="copia da un file locale invece di scaricare dal repository privato",
    )
    analizzatore.add_argument("--ref", default=RIF, help=f"revisione da scaricare (predefinito: {RIF})")
    argomenti = analizzatore.parse_args()

    destinazione = Path(argomenti.destinazione)
    if destinazione.exists():
        print(f"{destinazione} esiste già: non lo sovrascrivo. Cancellalo se vuoi riscaricarlo.")
        return

    if argomenti.da:
        copia_locale(Path(argomenti.da), destinazione)
    else:
        token = os.environ.get("PTF_DATI_TOKEN", "").strip()
        if not token:
            sys.exit(
                "Manca PTF_DATI_TOKEN.\n"
                "Due strade:\n"
                "  1. esporta il dataset da testfol.io e passalo con --da PERCORSO;\n"
                "  2. crea un fine-grained token con 'Contents: Read-only' sul "
                f"repository privato {REPOSITORY} e mettilo in PTF_DATI_TOKEN."
            )
        scarica(destinazione, token, argomenti.ref)

    righe = sum(1 for _ in destinazione.open(encoding="utf-8-sig"))
    print(f"Scritto {destinazione} ({destinazione.stat().st_size / 1024:.0f} KB, {righe} righe)")


if __name__ == "__main__":
    main()

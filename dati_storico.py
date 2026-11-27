"""Dove sta il dataset storico e come recuperarlo.

Il file `Timeseries.csv` non è nel repository: contiene serie esportate da testfol.io,
che ne ha autorizzato l'uso ma non la ridistribuzione (vedi PERMISSION.md). Il dataset
vive in un repository privato e arriva qui in due modi:

- in locale, accanto al codice (chi lo ha già esportato);
- in un ambiente senza il file (la demo su Streamlit Cloud), scaricandolo con un token
  di sola lettura messo nei secret dell'app o nella variabile `PTF_DATI_TOKEN`.

Questo modulo è l'unico punto che sa queste cose: l'app e lo script di scaricamento
lo usano, invece di ripetere percorsi e indirizzi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

NOME_FILE = "Timeseries.csv"
REPOSITORY_DATI = "TooBiggies/Portfolio-Backtester-dati"
PERCORSO_REMOTO = "Timeseries.csv"
# una serie di 49 anni in questo formato pesa oltre un megabyte: se arriva molto meno,
# il download è andato storto anche se il server ha risposto 200
DIMENSIONE_MINIMA = 200_000


def token_disponibile() -> str:
    """Token di sola lettura, dai secret di Streamlit oppure dall'ambiente."""
    try:
        import streamlit as st  # importato solo se l'app lo ha già caricato

        if "PTF_DATI_TOKEN" in st.secrets:
            return str(st.secrets["PTF_DATI_TOKEN"]).strip()
    except Exception:
        # fuori da Streamlit, o senza file dei secret: non è un errore
        pass
    return os.environ.get("PTF_DATI_TOKEN", "").strip()


def scarica(destinazione: Path, token: str, ref: str = "main") -> Path:
    """Scarica il CSV dal repository privato. Solleva RuntimeError con un messaggio leggibile."""
    indirizzo = f"https://api.github.com/repos/{REPOSITORY_DATI}/contents/{PERCORSO_REMOTO}?ref={ref}"
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
            raise RuntimeError(
                f"Il dataset non è stato trovato in {REPOSITORY_DATI}: "
                "controlla di avere accesso al repository privato."
            ) from errore
        if errore.code in (401, 403):
            raise RuntimeError(
                "Token non valido o senza permesso di lettura sul dataset: serve un "
                f"fine-grained token con 'Contents: Read-only' su {REPOSITORY_DATI}."
            ) from errore
        raise

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    destinazione.write_bytes(contenuto)
    if destinazione.stat().st_size < DIMENSIONE_MINIMA:
        destinazione.unlink(missing_ok=True)
        raise RuntimeError("Download del dataset incompleto: niente è stato scritto.")
    return destinazione


def percorso_dataset() -> Path:
    """Percorso di un dataset utilizzabile, scaricandolo se manca.

    Ordine: il file accanto al codice (caso locale), poi una copia nella cartella
    temporanea scaricata dal repository privato. Se non c'è né l'uno né l'altro e
    manca il token, solleva RuntimeError spiegando cosa fare.
    """
    locale = Path(__file__).with_name(NOME_FILE)
    if locale.exists():
        return locale

    cache = Path(tempfile.gettempdir()) / NOME_FILE
    if cache.exists() and cache.stat().st_size >= DIMENSIONE_MINIMA:
        return cache

    token = token_disponibile()
    if not token:
        raise RuntimeError(
            "Il dataset storico (Timeseries.csv) non è nel repository e non c'è un token "
            "per scaricarlo.\n\n"
            "Due strade:\n"
            "  • in locale: esporta le serie da testfol.io e mettile accanto al codice, "
            f"oppure lancia «python {Path(sys.argv[0]).name if sys.argv else 'scripts/scarica_dati.py'}» "
            "con PTF_DATI_TOKEN impostato;\n"
            "  • su Streamlit Cloud: aggiungi PTF_DATI_TOKEN nei secret dell'app."
        )
    return scarica(cache, token)

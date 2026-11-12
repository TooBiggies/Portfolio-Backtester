"""Finestra senza giorni di borsa: il motore deve dire perché, non sollevare IndexError.

Quattro modi di chiedere un intervallo in cui non c'è nessuna riga simulabile:
date tutte prima dei dati, tutte dopo, un solo giorno non di borsa, date invertite.
Prima di questa correzione usciva `IndexError: single positional indexer is out-of-bounds`
da `prices.iloc[0]`, che nell'app arrivava come traceback.
"""
from pathlib import Path

import pandas as pd
import pytest

from backtester import backtest

DATASET = str(Path(__file__).resolve().parent.parent / "Timeseries.csv")
PESI = {"VTSIM": 0.6, "GLDSIM": 0.1, "IEFSIM": 0.2, "DBMFSIM": 0.1}


def esegui(inizio, fine):
    return backtest(10_000.0, PESI, begin_date=inizio, end_date=fine,
                    data_path=DATASET, save_outputs=False)


@pytest.mark.parametrize("inizio,fine,motivo", [
    ("1950-01-02", "1960-12-30", "tutte prima dei dati"),
    ("2030-01-02", "2031-12-30", "tutte dopo i dati"),
    ("2024-03-09", "2024-03-09", "un sabato, giorno non di borsa"),
    ("2024-06-01", "2024-01-01", "date invertite"),
])
def test_finestra_vuota_solleva_un_errore_leggibile(inizio, fine, motivo):
    with pytest.raises(ValueError) as errore:
        esegui(inizio, fine)
    messaggio = str(errore.value)
    assert "Nessun giorno di borsa nella finestra richiesta" in messaggio, motivo
    # il messaggio deve dire anche dove sono i dati, altrimenti non aiuta a correggere
    assert "Il dataset copre dal" in messaggio, motivo
    assert "IndexError" not in messaggio


def test_il_messaggio_riporta_gli_estremi_del_dataset():
    """Gli estremi nel testo sono quelli veri, non un segnaposto."""
    with pytest.raises(ValueError) as errore:
        esegui("1950-01-02", "1960-12-30")
    dati = pd.read_csv(DATASET, sep=";")
    date = pd.to_datetime(dati["Date"], dayfirst=True, errors="coerce").dropna()
    assert str(date.min().date()) in str(errore.value)
    assert str(date.max().date()) in str(errore.value)


def test_una_finestra_valida_non_cambia_comportamento():
    """La guardia non deve toccare i casi normali."""
    _, _, s = esegui("2000-01-03", "2025-09-04")
    assert s["final_broker"] > 0
    assert s["years"] > 25

"""Esportazione: gli artefatti che l'utente archivia.

`save_outputs=True` scrive quattro file nella directory corrente. Erano l'unico pezzo
del percorso utente — quello che finisce in una cartella e viene riletto mesi dopo —
senza nessun test: se un giorno cambiano formato o nome, la suite resta verde e il file
sbagliato viene archiviato come se fosse giusto.
"""
from pathlib import Path

import pandas as pd
import pytest

from backtester import backtest

PESI = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}
# I file di output vanno nella cartella corrente (quella del test), i dati si leggono dal
# repository: i due percorsi sono indipendenti e vanno passati separatamente.
DATI = str(Path(__file__).resolve().parent.parent / "Timeseries.csv")


def esegui(cwd, **kwargs):
    return backtest(10000, PESI, begin_date=pd.Timestamp("2020-01-02"),
                    end_date=pd.Timestamp("2020-06-01"), save_outputs=True,
                    data_path=DATI, **kwargs)


def test_save_outputs_scrive_i_quattro_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    esegui(tmp_path)
    for nome in ("output_ptf.xlsx", "output_ptf_delta.xlsx", "output_ptf.csv", "output_ptf_delta.csv"):
        percorso = tmp_path / nome
        assert percorso.exists(), f"manca {nome}"
        assert percorso.stat().st_size > 0, f"{nome} e' vuoto"


def test_il_csv_esportato_e_identico_al_dataframe_restituito(tmp_path, monkeypatch):
    """Il file archiviato deve contenere gli stessi numeri del DataFrame che il motore
    restituisce: se divergono, l'utente rilegge fra un anno dei valori che non sono
    quelli che il programma ha calcolato."""
    monkeypatch.chdir(tmp_path)
    df_log, df_delta, summary = esegui(tmp_path)
    # parse_dates: senza, l'indice riletto e' una stringa e il confronto con il
    # DataFrame originale si allinea su 208 righe di NaN invece che sulle 104 vere.
    riletto = pd.read_csv(tmp_path / "output_ptf.csv", index_col=0, parse_dates=True)
    assert len(riletto) == len(df_log)
    assert list(riletto.columns) == list(df_log.columns)
    for colonna in ("BrokerPortfolioValue", "Net", "GrossPortfolioValue"):
        assert float((riletto[colonna] - df_log[colonna]).abs().max()) < 1e-6, colonna
    assert float(riletto["Net"].iloc[-1]) == pytest.approx(summary["final_net"], rel=1e-9)


def test_senza_save_outputs_non_sporca_la_cartella(tmp_path, monkeypatch):
    """Il default e' non scrivere niente: un run di prova non deve lasciare file in giro
    nella directory da cui e' stato lanciato."""
    monkeypatch.chdir(tmp_path)
    backtest(10000, PESI, begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2020-06-01"),
             save_outputs=False, data_path=DATI)
    assert list(tmp_path.iterdir()) == []

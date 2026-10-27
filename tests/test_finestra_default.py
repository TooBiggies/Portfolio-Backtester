"""Regressione sulla finestra temporale di default.

Emersa dai test della PR #64: `prepare_price_dataframe` calcolava l'intervallo con
`pd.to_datetime(...)` senza `dayfirst=True` e con `min()`/`max()` sulle **stringhe**.
Due conseguenze, entrambe silenziose:

- confronto alfabetico: "03/01/2021" < "29/12/2020", quindi a cavallo d'anno la
  finestra usciva rovesciata e il DataFrame risultava vuoto;
- lettura all'americana: senza `dayfirst=True` ogni data con giorno <= 12 veniva
  letta mese/giorno ("05/02/2020" = 2 maggio invece del 5 febbraio).
"""
import warnings

import pandas as pd
import pytest

from backtester import prepare_price_dataframe


def dataframe(date, valori=None):
    valori = valori if valori is not None else [100.0] * len(date)
    return pd.DataFrame({"Date": date, "AAA": valori})


def test_finestra_default_a_cavallo_danno_non_si_rovescia():
    """Prima: min() alfabetico = "03/01/2021", max() = "29/12/2020" -> nessuna riga."""
    prezzi, inizio, fine = prepare_price_dataframe(
        dataframe(["29/12/2020", "03/01/2021", "02/02/2021"]))
    assert inizio == pd.Timestamp("2020-12-29")
    assert fine == pd.Timestamp("2021-02-02")
    assert len(prezzi) == 3


def test_date_con_giorno_sotto_il_13_non_vengono_lette_all_americana():
    """Tutte le date hanno giorno <= 12: senza dayfirst=True sono ambigue."""
    prezzi, inizio, fine = prepare_price_dataframe(
        dataframe(["03/02/2020", "05/02/2020", "07/02/2020"]))
    assert inizio == pd.Timestamp("2020-02-03")
    assert fine == pd.Timestamp("2020-02-07")
    assert list(prezzi.index) == [pd.Timestamp("2020-02-03"), pd.Timestamp("2020-02-05"),
                                 pd.Timestamp("2020-02-07")]


def test_nessun_avviso_di_pandas_sul_formato_delle_date():
    with warnings.catch_warnings(record=True) as raccolti:
        warnings.simplefilter("always")
        prepare_price_dataframe(dataframe(["31/01/2020", "03/02/2020"]))
    assert not [w for w in raccolti if "dayfirst" in str(w.message)]


def test_la_finestra_ignora_le_righe_con_prezzi_mancanti():
    """Comportamento conservato: la finestra copre solo il tratto popolato."""
    prezzi, inizio, fine = prepare_price_dataframe(
        dataframe(["01/02/2020", "03/02/2020", "31/12/2021"], [100.0, 101.0, None]))
    assert fine == pd.Timestamp("2020-02-03")
    assert len(prezzi) == 2


def test_senza_date_valide_solleva_errore_invece_di_tornare_vuoto():
    with pytest.raises(ValueError, match="Nessuna data valida"):
        prepare_price_dataframe(dataframe(["non-una-data", "nemmeno-questa"]))


def test_una_data_esplicita_vince_sulla_finestra_calcolata():
    """Se le date sono passate, non si calcola nulla. Il tipo restituito resta quello
    ricevuto (stringa se stringa): la conversione degli ingressi e' materia della #49."""
    prezzi, inizio, fine = prepare_price_dataframe(
        dataframe(["03/02/2020", "05/02/2020", "07/02/2020"]),
        begin_date="2020-02-04", end_date="2020-02-06")
    assert pd.Timestamp(inizio) == pd.Timestamp("2020-02-04")
    assert pd.Timestamp(fine) == pd.Timestamp("2020-02-06")
    assert list(prezzi.index) == [pd.Timestamp("2020-02-05")]

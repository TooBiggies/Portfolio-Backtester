"""Regressione sulla finestra temporale di default.

I due difetti corretti in questa PR (confronto alfabetico delle date e lettura
all'americana) non avevano test: i test deterministici passano sempre date
esplicite, quindi una regressione sulla finestra calcolata non si sarebbe vista.

Difetti coperti:
- min()/max() sulle STRINGHE: "03/01/2021" < "29/12/2020" in ordine alfabetico,
  quindi a cavallo d'anno la finestra usciva rovesciata e il DataFrame era vuoto;
- pd.to_datetime senza dayfirst=True: ogni data con giorno <= 12 veniva letta
  mese/giorno ("05/02/2020" = 2 maggio).
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


def test_senza_date_valide_solleva_errore_invece_di_tornare_vuoto():
    with pytest.raises(ValueError, match="Nessuna data valida"):
        prepare_price_dataframe(dataframe(["non-una-data", "nemmeno-questa"]))


def test_una_data_esplicita_vince_sulla_finestra_calcolata():
    """Il tipo restituito resta quello ricevuto (stringa se stringa)."""
    prezzi, inizio, fine = prepare_price_dataframe(
        dataframe(["03/02/2020", "05/02/2020", "07/02/2020"]),
        begin_date="2020-02-04", end_date="2020-02-06")
    assert pd.Timestamp(inizio) == pd.Timestamp("2020-02-04")
    assert pd.Timestamp(fine) == pd.Timestamp("2020-02-06")
    assert list(prezzi.index) == [pd.Timestamp("2020-02-05")]


def test_una_riga_con_data_valida_e_prezzo_mancante_non_allarga_la_finestra():
    """La finestra di default copre solo il tratto in cui i dati esistono davvero:
    una riga con data valida e prezzo mancante non deve allungarla (issue #8)."""
    _, inizio, fine = prepare_price_dataframe(
        dataframe(["01/02/2020", "03/02/2020", "31/12/2021"], [100.0, 101.0, None]))
    assert inizio == pd.Timestamp("2020-02-01")
    assert fine == pd.Timestamp("2020-02-03")


def test_la_finestra_default_e_quella_comune_a_tutti_gli_asset():
    """Criterio di accettazione della issue #8: senza date, la data iniziale e' la meno
    recente fra quelle in comune a tutti gli asset in portafoglio."""
    df = pd.DataFrame({"Date": ["01/02/2020", "02/02/2020", "03/02/2020"],
                       "AAA": [1.0, 1.0, 1.0],
                       "BBB": [None, 1.0, 1.0]})
    prezzi, inizio, fine = prepare_price_dataframe(df, asset_columns=["AAA", "BBB"])
    assert inizio == pd.Timestamp("2020-02-02")
    assert fine == pd.Timestamp("2020-02-03")
    assert len(prezzi) == 2

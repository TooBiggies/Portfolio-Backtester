"""Conversioni di valuta e deflazione: le proprietà che devono valere sempre.

Sono test sulle identità, non sui numeri di una simulazione: il fattore di cambio deve
fare esattamente quello che dice, e la deflazione non deve toccare il primo giorno.
"""
from __future__ import annotations

import pandas as pd
import pytest

from valuta import VALUTE, carica_serie, converti_prezzi, fattore_cambio, fattore_deflazione

DATE = pd.date_range("2000-01-01", periods=4, freq="YS")


def scrivi_cambi(percorso, euro_dollaro, indice):
    tabella = pd.DataFrame({"Date": DATE, "EURUSD": euro_dollaro, "CPI_IT": indice})
    tabella.to_csv(percorso, sep=";", index=False, date_format="%d/%m/%Y")
    return percorso


@pytest.fixture()
def percorso(tmp_path):
    # Cambio fisso a 2 dollari per euro, inflazione al 10% l\'anno.
    return scrivi_cambi(tmp_path / "cambi.csv", [2.0] * 4, [100.0, 110.0, 121.0, 133.1])


@pytest.fixture()
def serie(percorso):
    return carica_serie(percorso)


@pytest.fixture()
def prezzi():
    return pd.DataFrame({"AAA": [10.0, 11.0, 12.0, 13.0],
                         "BBB": [20.0, 20.0, 20.0, 20.0]}, index=DATE)


def test_dollari_non_cambiano_niente(serie):
    assert (fattore_cambio("USD", DATE, serie) == 1.0).all()


def test_euro_divide_per_il_cambio(serie):
    # 2 dollari per euro: un dollaro vale mezzo euro.
    assert fattore_cambio("EUR", DATE, serie).iloc[0] == pytest.approx(0.5)


def test_la_lira_non_e_piu_una_valuta(serie):
    # La lira non è più selezionabile: l'euro copre anche il periodo ante-1999,
    # dove il cambio è ricostruito dalla lira al tasso irrevocabile.
    assert VALUTE == ("USD", "EUR")
    with pytest.raises(ValueError, match="lira"):
        fattore_cambio("ITL", DATE, serie)


def test_deflazione_vale_uno_il_primo_giorno(serie):
    fattore = fattore_deflazione(DATE, serie)
    assert fattore.iloc[0] == pytest.approx(1.0)
    # Dieci per cento l\'anno: dopo tre anni il potere d\'acquisto è 100/133,1.
    assert fattore.iloc[-1] == pytest.approx(100.0 / 133.1)


def test_conversione_preserva_i_rapporti_fra_asset(prezzi, percorso):
    """Il fattore è comune a tutte le colonne: i rapporti interni non possono cambiare."""
    convertiti = converti_prezzi(prezzi, valuta="EUR", percorso=percorso)
    prima = (prezzi["AAA"] / prezzi["BBB"]).to_numpy()
    dopo = (convertiti["AAA"] / convertiti["BBB"]).to_numpy()
    assert prima == pytest.approx(dopo)


def test_inflazione_riduce_il_potere_dacquisto(percorso):
    """Con prezzi nominali costanti, in termini reali il valore scende."""
    costante = pd.DataFrame({"AAA": [100.0] * 4}, index=DATE)
    reale = converti_prezzi(costante, valuta="USD", reale=True, percorso=percorso)
    assert reale["AAA"].iloc[0] == pytest.approx(100.0)
    assert reale["AAA"].iloc[-1] == pytest.approx(100.0 * 100.0 / 133.1)
    assert reale["AAA"].is_monotonic_decreasing


def test_conversione_e_deflazione_si_combinano(prezzi, percorso):
    """Euro reali = dollari / cambio x (prezzi iniziali / prezzi correnti)."""
    convertiti = converti_prezzi(prezzi, valuta="EUR", reale=True, percorso=percorso)
    atteso = 13.0 / 2.0 * (100.0 / 133.1)
    assert convertiti["AAA"].iloc[-1] == pytest.approx(atteso)


def test_valuta_sconosciuta_e_un_errore_esplicito(prezzi):
    with pytest.raises(ValueError, match="non gestita"):
        converti_prezzi(prezzi, valuta="GBP")


def test_finestra_non_coperta_e_un_errore_esplicito(percorso):
    prezzi = pd.DataFrame({"AAA": [1.0, 1.0]}, index=pd.date_range("1990-01-01", periods=2))
    with pytest.raises(ValueError, match="non copre la finestra"):
        converti_prezzi(prezzi, valuta="EUR", percorso=percorso)


def test_dollari_senza_deflazione_restituiscono_gli_stessi_prezzi(prezzi):
    """Percorso rapido: nessuna conversione, nessun file da leggere."""
    identici = converti_prezzi(prezzi, valuta="USD", reale=False, percorso="non-esiste.csv")
    pd.testing.assert_frame_equal(identici, prezzi)


def test_finestra_prima_del_cambio_viene_ritagliata():
    """Chi sceglie gli euro non può partire dal 1969: le serie di cambio cominciano nel 1971.

    Non è un errore dell'utente, è un limite dei dati: la simulazione parte dal primo
    giorno disponibile invece di fallire.
    """
    from backtester import backtest

    _, _, summary = backtest(
        initial_value=10_000.0,
        weights={"VTSIM": 1.0},
        begin_date="1969-12-31",
        end_date="1975-12-31",
        brokerage_fee_rate=0.001,
        annual_costs_rate=0.002,
        tax_rate=0.26,
        rebalance_threshold=0.05,
        rel_rebalance_threshold=0.2,
        risk_free_rate="CASHX",
        plot=False,
        save_outputs=False,
        valuta="EUR",
    )
    assert summary["valuta"] == "EUR"
    assert summary["begin_date"].year >= 1971
    assert summary["final_net"] > 0

# questi test leggono il dataset storico reale: senza Timeseries.csv si saltano
pytestmark = pytest.mark.dati

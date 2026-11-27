"""Test su lettura delle date, selezione degli asset e coerenza del log.

Il log giornaliero e' il foglio che finisce in Excel e su cui si fanno i conti a
mano: se le colonne per asset non sommano al totale di portafoglio, ogni verifica
successiva e' falsata.
"""
import os

import pandas as pd
import pytest

from backtester import backtest, prepare_price_dataframe

GREZZO = pd.DataFrame({
    "Date": ["31/01/2020", "03/02/2020", "28/02/2020", "02/03/2020"],
    "AAA": [100.0, 101.0, 102.0, 103.0],
    "BBB": [50.0, 51.0, 52.0, 53.0],
})


@pytest.fixture(autouse=True)
def nel_repo(monkeypatch):
    radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.chdir(radice)
    if not os.path.exists("Timeseries.csv"):
        pytest.skip("Timeseries.csv assente")


# --- lettura delle date ---------------------------------------------------

def test_date_in_formato_italiano_lette_con_il_giorno_prima_del_mese():
    """'31/01/2020' e' il 31 gennaio, non il 3 novembre."""
    prezzi, inizio, fine = prepare_price_dataframe(GREZZO.copy(), begin_date="2020-01-01",
                                                   end_date="2020-12-31")
    assert prezzi.index[0] == pd.Timestamp("2020-01-31")
    assert prezzi.index[-1] == pd.Timestamp("2020-03-02")


def test_la_finestra_esclude_le_righe_fuori_intervallo():
    """Una finestra di febbraio non deve includere il 31 gennaio: confrontando le
    date come stringhe ('31/01/2020' > '01/02/2020') ci finiva dentro."""
    prezzi, _, _ = prepare_price_dataframe(GREZZO.copy(), begin_date="2020-02-01",
                                           end_date="2020-02-29")
    assert list(prezzi.index) == [pd.Timestamp("2020-02-03"), pd.Timestamp("2020-02-28")]


def test_la_finestra_accetta_timestamp_e_stringhe():
    a, _, _ = prepare_price_dataframe(GREZZO.copy(), begin_date=pd.Timestamp("2020-02-01"),
                                      end_date=pd.Timestamp("2020-02-29"))
    b, _, _ = prepare_price_dataframe(GREZZO.copy(), begin_date="2020-02-01",
                                      end_date="2020-02-29")
    assert a.equals(b)


def test_vengono_restituite_solo_le_colonne_richieste():
    prezzi, _, _ = prepare_price_dataframe(GREZZO.copy(), asset_columns=["AAA"])
    assert list(prezzi.columns) == ["AAA"]


def test_una_finestra_vuota_restituisce_un_dataframe_vuoto():
    prezzi, _, _ = prepare_price_dataframe(GREZZO.copy(), begin_date="2021-01-01",
                                           end_date="2021-12-31")
    assert len(prezzi) == 0


# --- coerenza del log giornaliero ----------------------------------------

def esegui(threshold=0.1):
    return backtest(10000, {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05},
                    begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2021-01-04"),
                    brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26,
                    rebalance_threshold=threshold, save_outputs=False)[0]


def colonne(risultati, prefisso):
    return [c for c in risultati.columns if c.startswith(prefisso)]


def test_le_colonne_per_asset_sommano_al_totale():
    r = esegui()
    for prefisso, totale in (("Broker_", "BrokerPortfolioValue"),
                             ("Net_", "Net"),
                             ("Gross_", "GrossPortfolioValue")):
        somma = r[colonne(r, prefisso)].sum(axis=1)
        assert somma.equals(r[totale].astype(somma.dtype)) or (
            (somma - r[totale]).abs().max() < 1e-6), prefisso


def test_il_netto_non_supera_mai_il_broker():
    r = esegui()
    assert (r["Net"] <= r["BrokerPortfolioValue"] + 1e-9).all()


def test_il_lordo_non_e_mai_sotto_il_broker():
    r = esegui()
    assert (r["GrossPortfolioValue"] >= r["BrokerPortfolioValue"] - 1e-9).all()


def test_i_costi_di_detenzione_sono_addebitati_ogni_giorno():
    r = esegui()
    costi = colonne(r, "HoldingCost_")
    assert costi
    assert (r[costi].abs().sum(axis=1) > 0).all()


def test_i_costi_di_transazione_esistono_solo_nei_giorni_di_ribilanciamento():
    """Con soglia alta i ribilanciamenti sono rari: i giorni con costo di
    transazione devono essere una minoranza, non tutti."""
    r = esegui(threshold=0.1)
    costi = colonne(r, "TradeCost_")
    giorni_con_costo = (r[costi].abs().sum(axis=1) > 0).sum()
    assert 0 < giorni_con_costo < len(r) / 2


def test_senza_vendite_in_guadagno_non_ci_sono_imposte():
    """Pesi costanti su un solo asset, nessun ribilanciamento: nessuna imposta."""
    r = backtest(10000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"),
                 end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0029,
                 annual_costs_rate=0.002, tax_rate=0.26, rebalance_threshold=0.5,
                 save_outputs=False)[0]
    imposte = colonne(r, "Tax_")
    assert r[imposte].abs().to_numpy().sum() == pytest.approx(0.0, abs=1e-9)

"""Conservazione del valore e coerenza del log: le identita' che rendono il report vero.

`df_log` e' il foglio Excel che l'utente scarica. Se una colonna aggregata non e' la
somma delle sue colonne per asset, il file racconta due storie diverse e nessuno se ne
accorge: i numeri sono plausibili, solo sbagliati. Nessuno di questi controlli esisteva.
"""
import pandas as pd
import pytest

from backtester import backtest

PESI = {"VTSIM": 0.60, "GLDSIM": 0.10, "ZROZSIM": 0.25, "DBMFSIM": 0.05}
INIZIO = pd.Timestamp("2020-01-02")
FINE = pd.Timestamp("2021-01-04")


def esegui(**kwargs):
    return backtest(10000, PESI, begin_date=INIZIO, end_date=FINE, save_outputs=False, **kwargs)


def test_gli_aggregati_sono_la_somma_delle_colonne_per_asset():
    df, _, _ = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    for aggregato, prefisso in (("BrokerPortfolioValue", "Broker_"), ("Net", "Net_"),
                                ("GrossPortfolioValue", "Gross_")):
        colonne = [c for c in df.columns if c.startswith(prefisso)]
        assert colonne, f"nessuna colonna {prefisso}*"
        massimo_scarto = float((df[aggregato] - df[colonne].sum(axis=1)).abs().max())
        assert massimo_scarto < 1e-6, f"{aggregato} non e' la somma di {prefisso}*: scarto {massimo_scarto}"


def test_i_costi_di_detenzione_sono_proporzionali_al_valore_di_ogni_asset():
    """HoldingCost_<asset> deve essere controvalore x un coefficiente **costante nel
    tempo e uguale per tutti gli asset**: e' il punto in cui si vede se il costo annuo
    viene applicato per asset o per sbaglio sul totale del portafoglio.

    Il valore del coefficiente e' verificato nel test successivo.
    """
    df, _, _ = esegui(brokerage_fee_rate=0.0, annual_costs_rate=0.002, tax_rate=0.0)
    coefficienti = {}
    for colonna in [c for c in df.columns if c.startswith("HoldingCost_")]:
        asset = colonna.replace("HoldingCost_", "")
        rapporto = (df[colonna] / df[f"Broker_{asset}"]).dropna()
        assert float((rapporto - rapporto.iloc[0]).abs().max()) < 1e-12, f"{colonna} non e' costante"
        coefficienti[asset] = float(rapporto.iloc[0])
    assert max(coefficienti.values()) - min(coefficienti.values()) < 1e-15, (
        f"coefficiente diverso fra asset: {coefficienti}")


@pytest.mark.xfail(strict=False, reason=(
    "Su develop il bollo e' un parametro separato con default 0,20%: scrivere 0,2% nei "
    "costi annui fa pagare 0,4% (0,1% sui costi + 0,1% sul bollo), cioe' il doppio. "
    "Questo caso diventa verde con la #77, che porta il bollo dentro i costi annui. "
    "Lasciato come xfail non-strict: su develop documenta il difetto, dopo il merge passa "
    "senza rumore."))
def test_i_costi_di_detenzione_corrispondono_al_tasso_scritto_dall_utente():
    """Quello che l'utente scrive deve essere quello che paga: 0,2% annuo = 0,2%/252 al giorno."""
    df, _, _ = esegui(brokerage_fee_rate=0.0, annual_costs_rate=0.002, tax_rate=0.0)
    colonna = "HoldingCost_VTSIM"
    rapporto = float((df[colonna] / df["Broker_VTSIM"]).dropna().iloc[0])
    assert rapporto == pytest.approx(0.002 / 252, rel=1e-12), (
        f"costo giornaliero {rapporto} invece di {0.002/252}: "
        f"annuo effettivo {rapporto*252:.4f} invece di 0.0020")


def test_il_netto_non_supera_mai_il_broker_il_lordo_non_e_mai_sotto():
    """Ordine dei tre valori, riga per riga: il lordo non paga nulla, il broker paga i
    costi, il netto paga anche l'uscita. Se l'ordine si inverte, una delle tre serie
    sta contando un costo con il segno sbagliato."""
    df, _, _ = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    assert (df["Net"] <= df["BrokerPortfolioValue"] + 1e-9).all()
    assert (df["GrossPortfolioValue"] >= df["BrokerPortfolioValue"] - 1e-9).all()
    assert (df["Net"] >= 0).all()


def test_alla_data_iniziale_i_soldi_spesi_piu_le_commissioni_fanno_il_capitale():
    """La prima riga del log deve chiudere in contanti: quello che e' stato comprato
    piu' le commissioni pagate deve valere esattamente il capitale iniziale."""
    df, _, _ = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    prima = df.iloc[0]
    commissioni = -float(prima[[c for c in df.columns if c.startswith("TradeCost_")]].sum())
    assert prima["BrokerPortfolioValue"] + commissioni == pytest.approx(10000.0, rel=1e-9)


def test_con_aliquota_zero_netto_e_broker_coincidono():
    """Senza imposte l'unica differenza fra netto e broker sono le commissioni di uscita,
    che il motore conta come costo: azzerando anche quelle i due valori devono coincidere.
    E' la prova che il 'netto' non contiene altro oltre a costi e imposte."""
    df, _, _ = esegui(brokerage_fee_rate=0.0, annual_costs_rate=0.0, tax_rate=0.0)
    assert float((df["Net"] - df["BrokerPortfolioValue"]).abs().max()) < 1e-9


def test_il_log_segue_i_giorni_di_contrattazione_della_finestra():
    df, _, summary = esegui(brokerage_fee_rate=0.0029)
    date = pd.to_datetime(df.index)
    assert date.is_monotonic_increasing
    assert len(date) == len(set(date)), "date duplicate nel log"
    assert date[0] == INIZIO
    assert date[-1] <= FINE
    assert summary["begin_date"] == date[0] and summary["end_date"] == date[-1]


def test_il_riepilogo_coincide_con_l_ultima_riga_del_log():
    """Se `summary` e `df_log` divergono, il numero stampato e quello esportato sono
    due cose diverse: l'utente legge il primo e archivia il secondo."""
    df, _, summary = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    ultima = df.iloc[-1]
    assert summary["final_gross"] == pytest.approx(ultima["GrossPortfolioValue"], rel=1e-12)
    assert summary["final_broker"] == pytest.approx(ultima["BrokerPortfolioValue"], rel=1e-12)
    assert summary["final_net"] == pytest.approx(ultima["Net"], rel=1e-12)

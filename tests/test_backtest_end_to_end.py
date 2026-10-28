"""Test end-to-end di backtest() sul Timeseries.csv reale.

Verificano le proprieta' che devono valere per qualunque configurazione
(invarianti, monotonia, conservazione) invece di fissare un numero: un numero
fissato dice che il risultato non e' cambiato, non che e' giusto.
I numeri di riferimento restano in tests/test_backtest_deterministico.py.
"""
import os
import shutil

import pandas as pd
import pytest

from backtester import backtest

W = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}
PERIODO = dict(begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2023-01-02"))
COSTI = dict(brokerage_fee_rate=0.0029, annual_costs_rate=0.002)


@pytest.fixture(autouse=True)
def nel_repo(monkeypatch):
    """backtest() legge './Timeseries.csv': i test lo eseguono dalla radice del repo."""
    radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.chdir(radice)
    if not os.path.exists("Timeseries.csv"):
        pytest.skip("Timeseries.csv assente: test end-to-end non eseguibili")


def esegui(**kwargs):
    parametri = {**dict(initial_value=10000, weights=W, save_outputs=False), **kwargs}
    return backtest(**parametri)


# --- determinismo e invarianti -------------------------------------------

def test_due_esecuzioni_identiche_danno_gli_stessi_numeri():
    _, _, a = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    _, _, b = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    for chiave in ("final_gross", "final_broker", "final_net", "cagr_net", "years"):
        assert a[chiave] == b[chiave]


def test_lordo_maggiore_del_broker_maggiore_del_netto():
    """Ogni livello di costo puo' solo togliere valore: non puo' esistere un netto
    sopra il broker o un broker sopra il lordo."""
    _, _, s = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    assert s["final_gross"] > s["final_broker"] > s["final_net"]


def test_il_lordo_non_dipende_dai_parametri_fiscali():
    """Il portafoglio ideale non paga imposte: aliquota 0 o 50% devono dare lo stesso lordo."""
    lordi = [esegui(tax_rate=t, **PERIODO, **COSTI)[2]["final_gross"] for t in (0.0, 0.26, 0.50)]
    assert lordi == pytest.approx([lordi[0]] * 3, rel=0, abs=1e-6)


def test_il_netto_decresce_al_crescere_dellaliquota():
    netti = [esegui(tax_rate=t, **PERIODO, **COSTI)[2]["final_net"] for t in (0.0, 0.26, 0.50)]
    assert netti[0] > netti[1] > netti[2]


def test_con_aliquota_zero_non_si_paga_alcuna_imposta():
    risultati, _, _ = esegui(tax_rate=0.0, **PERIODO, **COSTI)
    colonne_imposte = [c for c in risultati.columns if c.startswith("Tax_")]
    assert colonne_imposte
    assert risultati[colonne_imposte].abs().to_numpy().sum() == pytest.approx(0.0, abs=1e-9)


# --- coerenza interna dei risultati --------------------------------------

def test_valori_finali_coincidono_con_l_ultima_riga_del_log():
    risultati, _, s = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    assert s["final_net"] == pytest.approx(risultati["Net"].iloc[-1])
    assert s["final_broker"] == pytest.approx(risultati["BrokerPortfolioValue"].iloc[-1])
    assert s["final_gross"] == pytest.approx(risultati["GrossPortfolioValue"].iloc[-1])


def test_gli_anni_sono_quelli_effettivamente_simulati():
    """Se la serie parte dopo la data richiesta, gli anni sono quelli dei dati."""
    risultati, _, s = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    atteso = round((risultati.index[-1] - risultati.index[0]).days / 365.25, 2)
    assert s["years"] == pytest.approx(atteso)


def test_cagr_coerente_col_valore_finale():
    _, _, s = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    atteso = (s["final_net"] / 10000) ** (1 / s["years"]) - 1
    assert s["cagr_net"] == pytest.approx(atteso, rel=1e-3)


def test_metriche_di_rischio_coerenti_col_percorso_netto():
    risultati, _, s = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    m = s["risk_metrics"]["net"]
    for chiave in ("volatility", "max_drawdown", "sharpe", "sortino"):
        assert chiave in m
    assert m["volatility"] > 0
    assert -1 < m["max_drawdown"] < 0
    serie = risultati["Net"]
    ribasso = (serie / serie.cummax() - 1).min()
    assert m["max_drawdown"] == pytest.approx(ribasso, rel=1e-6)


# --- allocazione e ribilanciamento ---------------------------------------

def test_i_pesi_richiesti_sono_quelli_di_partenza():
    risultati, _, _ = esegui(tax_rate=0.26, **PERIODO, **COSTI)
    prima = risultati.iloc[0]
    totale = prima["BrokerPortfolioValue"]
    for asset, peso in W.items():
        assert prima[f"Broker_{asset}"] / totale == pytest.approx(peso, abs=1e-9)


# I pesi che non sommano a 1 sono coperti da tests/test_validazione_ingressi.py (PR #72),
# che li rifiuta in ingresso: qui non ha piu' senso misurare cosa succede dopo, perche'
# backtest() non arriva a simulare.

def test_soglia_altissima_non_produce_ribilanciamenti():
    risultati, _, _ = esegui(tax_rate=0.26, rebalance_threshold=1.0, **PERIODO, **COSTI)
    costi = [c for c in risultati.columns if c.startswith("TradeCost_")]
    assert risultati[costi].iloc[1:].abs().to_numpy().sum() == pytest.approx(0.0, abs=1e-9)


def test_soglia_bassa_produce_ribilanciamenti():
    risultati, _, _ = esegui(tax_rate=0.26, rebalance_threshold=0.01, **PERIODO, **COSTI)
    costi = [c for c in risultati.columns if c.startswith("TradeCost_")]
    assert risultati[costi].iloc[1:].abs().to_numpy().sum() > 0.0


# --- validazione degli ingressi ------------------------------------------

def test_finestra_non_coperta_da_un_asset_solleva_errore():
    """Un asset attivo senza prezzi nella finestra deve fermare il backtest, non
    produrre un capitale finale 0.00."""
    with pytest.raises(ValueError, match="KMLMSIM"):
        esegui(weights={"KMLMSIM": 1.0}, tax_rate=0.0,
               begin_date=pd.Timestamp("1990-01-02"), end_date=pd.Timestamp("2025-09-01"))


# --- scrittura degli output ----------------------------------------------

def test_save_outputs_scrive_i_file_attesi(tmp_path):
    shutil.copy("Timeseries.csv", tmp_path / "Timeseries.csv")
    os.chdir(tmp_path)
    esegui(tax_rate=0.26, begin_date=pd.Timestamp("2020-01-02"),
           end_date=pd.Timestamp("2020-06-01"), save_outputs=True)
    for nome in ("output_ptf.csv", "output_ptf_delta.csv", "plot.png"):
        assert (tmp_path / nome).exists(), f"manca {nome}"


def test_save_outputs_false_non_scrive_nulla(tmp_path):
    shutil.copy("Timeseries.csv", tmp_path / "Timeseries.csv")
    os.chdir(tmp_path)
    esegui(tax_rate=0.26, begin_date=pd.Timestamp("2020-01-02"),
           end_date=pd.Timestamp("2020-06-01"), save_outputs=False)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Timeseries.csv"]

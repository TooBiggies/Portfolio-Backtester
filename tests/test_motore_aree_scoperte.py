"""Test su aree del motore che nessun test toccava.

Criterio: parti di `engine.py` / `backtester.py` / `metrics.py` che non erano coperte
da nessun caso e su cui non era ancora emerso un difetto. Alcune hanno rivelato un
difetto vero (marcato `xfail` con il numero di issue), le altre fissano comportamenti
che oggi sono corretti ma che nessuno proteggeva.
"""
import contextlib
import signal

import pandas as pd
import pytest

from backtester import backtest, prepare_price_dataframe
from engine import Portfolio, Rebalancer
from metrics import periods_per_year


@contextlib.contextmanager
def scadenza(secondi):
    """Interrompe un blocco che non termina: serve per fissare un loop infinito come test."""
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("SIGALRM non disponibile su questa piattaforma")

    def scaduto(*_):
        raise TimeoutError(f"il blocco non e' terminato entro {secondi}s")

    signal.signal(signal.SIGALRM, scaduto)
    signal.alarm(secondi)
    try:
        yield
    finally:
        signal.alarm(0)


# --- transazioni simulate ------------------------------------------------

def test_simulate_transactions_ripristina_lo_stato_dopo_un_eccezione():
    """Il contesto serve a stimare i costi senza muovere il portafoglio: se il corpo
    solleva un'eccezione, quote e costi devono tornare quelli di prima."""
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.0)
    quote, costi = pf.holdings.copy(), pf.assets_costs.copy()
    with pytest.raises(RuntimeError):
        with pf.simulate_transactions() as temp:
            temp.sell(20.0, "A", 10)
            raise RuntimeError("dentro il contesto")
    assert pf.holdings.equals(quote)
    assert pf.assets_costs.equals(costi)


def test_simulate_transactions_non_lascia_tracce_nell_uso_normale():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.0)
    prima = pf.holdings.copy()
    with pf.simulate_transactions() as temp:
        temp.sell(20.0, "A", 50)
    assert pf.holdings.equals(prima)


# --- casi limite del portafoglio -----------------------------------------

def test_pmc_di_un_asset_non_detenuto_e_zero():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 1.0, "B": 0.0}, 0.0, 0.0)
    assert pf.pmc["B"] == 0.0          # nessuna divisione per zero


def test_cash_out_costs_di_un_portafoglio_vuoto_sono_zero():
    pf = Portfolio(prices=pd.Series({"A": 10.0, "B": 5.0}), initial_value=1000,
                   brokerage_fee_rate=0.01, tax_rate=0.26)
    assert (pf.cash_out_costs() == 0.0).all()


def test_i_costi_di_detenzione_applicati_due_volte_si_moltiplicano():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.002)
    fattore = 1.0 - float(pf.ter["A"] + pf.bollo["A"])
    quote = float(pf.holdings["A"])
    pf.apply_holding_costs()
    pf.apply_holding_costs()
    assert float(pf.holdings["A"]) == pytest.approx(quote * fattore ** 2)


def test_weights_di_un_asset_azzerato_sono_zero_mentre_gli_altri_sommano_a_uno():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 1.0, "B": 0.0}, 0.0, 0.0)
    assert pf.weights["B"] == 0.0
    assert float(pf.weights.sum()) == pytest.approx(1.0)


# --- ribilanciamento ai bordi --------------------------------------------

def test_soglia_zero_su_un_portafoglio_gia_a_target_non_produce_trade():
    """Il caso limite della soglia: nessuna deviazione, nessun ordine, e soprattutto
    nessun ciclo che rincorre la convergenza."""
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    with scadenza(10):
        costi, imposte, trades = Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.0,
                                            tax_rate=0.0).rebalance(pf)
    assert max(abs(v) for v in trades.values()) < 1e-9
    assert max(abs(v) for v in costi.values()) < 1e-12


# --- metriche su serie irregolari ---------------------------------------

def test_periodi_per_anno_con_due_date_a_trenta_giorni():
    """Una serie sparsa di due punti: la funzione deve dedurre ~12 periodi, non esplodere."""
    assert periods_per_year(pd.DatetimeIndex(["2020-01-01", "2020-01-31"])) == 12


def test_periodi_per_anno_con_date_ripetute_torna_un_valore_utile():
    idx = pd.DatetimeIndex(["2020-01-01", "2020-01-01"])
    assert periods_per_year(idx) == 252      # span zero: si ricade sul default


# --- ingressi sbagliati --------------------------------------------------

def test_un_asset_nei_pesi_che_non_esiste_nel_file_solleva_errore():
    """Oggi il messaggio arriva da pandas ("['NON_ESISTE'] not in index") e non dice
    che il problema e' un ticker sbagliato nei pesi: il test fissa che l'errore ci sia,
    non la sua forma, cosi' il messaggio si puo' migliorare senza rompere nulla."""
    with pytest.raises(KeyError):
        backtest(10000, {"VTSIM": 0.5, "NON_ESISTE": 0.5},
                 begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2020-02-03"),
                 save_outputs=False)


def test_una_colonna_richiesta_assente_solleva_errore():
    grezzo = pd.DataFrame({"Date": ["01/02/2020"], "AAA": [1.0]})
    with pytest.raises(KeyError):
        prepare_price_dataframe(grezzo, asset_columns=["AAA", "BBB"])


@pytest.mark.xfail(strict=False, reason="Issue #66: capitale iniziale 0 -> ciclo infinito "
                   "nel ribilanciamento (V'/V = 0/0 = NaN, la convergenza non arriva mai). "
                   "Quando backtest() rifiutera' un capitale non positivo questo test passera' "
                   "e il marcatore va tolto.")
def test_capitale_iniziale_zero_viene_rifiutato_subito():
    with scadenza(8), pytest.raises(ValueError):
        backtest(0, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"),
                 end_date=pd.Timestamp("2020-03-02"), save_outputs=False)


@pytest.mark.xfail(strict=False, reason="Issue #66: capitale negativo -> ValueError "
                   "«Cannot sell more than held», che non dice nulla sul capitale.")
def test_capitale_negativo_viene_rifiutato_con_messaggio_chiaro():
    with pytest.raises(ValueError, match="capitale"):
        backtest(-1000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"),
                 end_date=pd.Timestamp("2020-03-02"), save_outputs=False)

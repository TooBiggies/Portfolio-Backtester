"""Uscita dal portafoglio e ribilanciamento: due punti dove nessuno aveva guardato.

`cash_out_costs` e' quello che distingue il "broker" dal "netto": se sbaglia, il numero
che l'utente legge come capitale netto e' sbagliato di tutto il conto delle imposte.
Il `Rebalancer` e' il pezzo che genera le operazioni: un errore li' non si vede, si
manifesta come un rendimento leggermente diverso.

Nessuna delle proprieta' qui sotto era fissata da un test.
"""
import pandas as pd
import pytest

from engine import Portfolio, Rebalancer


def portafoglio_con_guadagno(tasso_commissione=0.0, prezzo_finale=200.0):
    """5 quote comprate a 100 (PMC 100), poi il prezzo raddoppia."""
    pf = Portfolio(prices=pd.Series({"A": 100.0}), initial_value=1000,
                   brokerage_fee_rate=tasso_commissione, tax_rate=0.26)
    pf.buy(100.0, "A", 5.0)
    pf.prices = pd.Series({"A": prezzo_finale})
    return pf


# ------------------------------------------------------------- cash_out_costs

def test_l_uscita_paga_il_26_per_cento_solo_sul_guadagno():
    """5 quote da PMC 100 a 200: guadagno 500, imposta 130, commissione 0."""
    costi = portafoglio_con_guadagno().cash_out_costs()
    assert costi["A"] == pytest.approx(130.0)


def test_la_commissione_di_uscita_si_somma_all_imposta():
    costi = portafoglio_con_guadagno(tasso_commissione=0.0029).cash_out_costs()
    assert costi["A"] == pytest.approx(130.0 + 200.0 * 5 * 0.0029)


def test_in_perdita_non_si_paga_imposta_ma_si_paga_la_commissione():
    """Una posizione in perdita non genera imposta (la perdita non si tassa) ma
    l'operazione costa: e' il caso in cui il netto e' piu' basso del broker senza che
    ci sia alcun guadagno da tassare."""
    costi = portafoglio_con_guadagno(tasso_commissione=0.0029, prezzo_finale=50.0).cash_out_costs()
    assert costi["A"] == pytest.approx(50.0 * 5 * 0.0029)


def test_chiedere_il_costo_di_uscita_non_vende_niente():
    """La stima usa una simulazione: se lasciasse il portafoglio modificato, ogni
    chiamata (una per giorno, per ogni asset) svuoterebbe il conto."""
    pf = portafoglio_con_guadagno(tasso_commissione=0.0029)
    quote_prima = pf.holdings.copy()
    costi_prima = pf.assets_costs.copy()
    pf.cash_out_costs()
    assert (pf.holdings == quote_prima).all()
    assert (pf.assets_costs == costi_prima).all()
    assert ppv(pf) == pytest.approx(1000.0)


def ppv(pf):
    return float(pf.broker_assets_value)


def test_il_netto_e_il_broker_meno_il_costo_di_uscita():
    """L'identita' che lega le due colonne del report, verificata sul portafoglio vero."""
    pf = portafoglio_con_guadagno(tasso_commissione=0.0029)
    assert pf.net_assets_value == pytest.approx(pf.broker_assets_value - pf.cash_out_costs().sum())


def test_con_aliquota_zero_l_uscita_costa_solo_la_commissione():
    pf = Portfolio(prices=pd.Series({"A": 200.0}), initial_value=1000,
                   brokerage_fee_rate=0.0029, tax_rate=0.0)
    pf.buy(100.0, "A", 5.0)
    costi = pf.cash_out_costs()
    assert costi["A"] == pytest.approx(200.0 * 5 * 0.0029)


# ----------------------------------------------------------------- Rebalancer

def nuovo_portafoglio(tasso_commissione=0.0):
    return Portfolio.from_weights(pd.Series({"A": 100.0, "B": 50.0}), 1000,
                                  {"A": 0.5, "B": 0.5}, tasso_commissione, 0.0)[0]


def test_dentro_la_soglia_il_ribilanciatore_non_tocca_niente():
    pf = nuovo_portafoglio()
    costi, imposte, delta = Rebalancer({"A": 0.5, "B": 0.5}, threshold=0.05).rebalance(pf)
    assert all(abs(v) < 1e-12 for v in delta.values())
    assert all(abs(v) < 1e-12 for v in costi.values())
    assert all(abs(v) < 1e-12 for v in imposte.values())


def test_ribilanciare_due_volte_di_fila_la_seconda_non_fa_niente():
    """Idempotenza: dopo un ribilanciamento i pesi sono sul target, quindi una seconda
    chiamata immediata non deve generare ordini. Se ne genera, il criterio di soglia
    sta misurando qualcosa che non e' la distanza dal target."""
    pf = nuovo_portafoglio()
    pf.prices = pd.Series({"A": 200.0, "B": 50.0})        # pesi sbilanciati 0,80 / 0,20
    ribilanciatore = Rebalancer({"A": 0.5, "B": 0.5}, threshold=0.05)
    _, _, primo = ribilanciatore.rebalance(pf)
    assert any(abs(v) > 1.0 for v in primo.values()), "il primo giro doveva operare"

    _, _, secondo = ribilanciatore.rebalance(pf)
    assert all(abs(v) < 1e-6 for v in secondo.values()), f"il secondo giro ha operato: {secondo}"


def test_dopo_il_ribilanciamento_i_pesi_sono_piu_vicini_al_target():
    pf = nuovo_portafoglio()
    pf.prices = pd.Series({"A": 200.0, "B": 50.0})
    prima = float((pf.weights - pd.Series({"A": 0.5, "B": 0.5})).abs().max())
    Rebalancer({"A": 0.5, "B": 0.5}, threshold=0.05).rebalance(pf)
    dopo = float((pf.weights - pd.Series({"A": 0.5, "B": 0.5})).abs().max())
    assert dopo < prima
    assert dopo < 0.01


def test_la_cassa_del_ribilanciamento_chiude_esattamente():
    """Conservazione di cassa: il ricavato delle vendite deve finanziare esattamente gli
    acquisti piu' costi e imposte (entrambi registrati con segno negativo).

        vendite - acquisti = costi + imposte
        sum(delta)         = sum(costi) + sum(imposte)

    Se la somma non chiude, il motore crea o distrugge denaro a ogni operazione e il
    "valore finale" e' falso di quella quantita' moltiplicata per ogni ribilanciamento.

    Con i numeri di questo caso: venduto 267,38, comprato 231,17, differenza 36,21 =
    34,76 di imposta + 1,45 di commissioni.

    La tolleranza non e' zero perche' il ribilanciamento e' un punto fisso (V dipende
    dalle imposte, le imposte dalle vendite, le vendite da V) che si ferma a 1e-8
    relativo: l'errore residuo qui e' 2,5e-6 su 1.500, cioe' 7 centesimi di milionesimo.
    """
    pf = nuovo_portafoglio(tasso_commissione=0.0029)
    pf.prices = pd.Series({"A": 200.0, "B": 50.0})
    valore_prima = float(pf.broker_assets_value)
    costi, imposte, delta = Rebalancer({"A": 0.5, "B": 0.5}, threshold=0.05).rebalance(pf)
    assert sum(delta.values()) == pytest.approx(sum(costi.values()) + sum(imposte.values()), abs=1e-4)
    # ...e il calo del valore di portafoglio e' esattamente quello che e' uscito per costi
    assert pf.broker_assets_value - valore_prima == pytest.approx(
        sum(costi.values()) + sum(imposte.values()), abs=1e-4)


def test_chi_vende_in_guadagno_paga_l_imposta_chi_compra_no():
    pf = nuovo_portafoglio()
    pf.prices = pd.Series({"A": 200.0, "B": 50.0})        # A sale: va venduto
    costi, imposte, delta = Rebalancer({"A": 0.5, "B": 0.5}, threshold=0.05).rebalance(pf)
    assert imposte["A"] < 0, "vendendo in guadagno l'imposta deve essere un costo"
    assert imposte["B"] == 0, "comprando non si paga imposta"
    assert delta["A"] < 0 < delta["B"], f"segni delle operazioni invertiti: {delta}"

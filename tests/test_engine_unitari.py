"""Test unitari del motore su dati sintetici.

Nessun file esterno, nessuna rete: ogni caso ha un risultato calcolabile a mano.
Servono a fissare l'aritmetica di Portfolio e Rebalancer, che i test end-to-end
coprono solo indirettamente (su 15 anni di dati un errore di PMC o di tassa
sposta il risultato di qualche euro e non si vede).
"""
import pandas as pd
import pytest

from engine import Portfolio, Rebalancer


def nuovo_portafoglio(prices, value=1000.0, fee=0.0, tax=0.0):
    return Portfolio(prices=pd.Series(prices, dtype="float64"), initial_value=value,
                     brokerage_fee_rate=fee, ter=None, tax_rate=tax)


# --- allocazione iniziale -------------------------------------------------

def test_from_weights_alloca_i_pesi_richiesti_senza_commissioni():
    pf, fees = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                      {"A": 0.6, "B": 0.4}, 0.0, 0.0)
    assert pf.holdings["A"] == pytest.approx(60.0)
    assert pf.holdings["B"] == pytest.approx(40.0)
    assert pf.broker_assets_value == pytest.approx(1000.0)
    assert pf.weights["A"] == pytest.approx(0.6)
    assert all(abs(v) < 1e-12 for v in fees.values())


def test_le_commissioni_riducono_il_capitale_investito_non_i_pesi():
    """Con fee f su un versamento V, il controvalore investito e' V/(1+f): il costo
    e' pagato dal capitale, non dall'allocazione."""
    pf, fees = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                      {"A": 0.6, "B": 0.4}, 0.01, 0.0)
    assert pf.broker_assets_value == pytest.approx(1000 / 1.01)
    assert sum(fees.values()) == pytest.approx(-(1000 - 1000 / 1.01))
    assert pf.weights["A"] == pytest.approx(0.6)


def test_asset_inesistente_nei_prezzi_viene_ignorato():
    pf, fees = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    assert pf.broker_assets_value == pytest.approx(500.0)
    assert "B" not in fees


# --- acquisti, PMC, vendite ----------------------------------------------

def test_pmc_e_la_media_ponderata_degli_acquisti():
    pf = nuovo_portafoglio({"A": 10.0})
    pf.buy(10.0, "A", 10)      # 100 EUR a PMC 10
    pf.buy(20.0, "A", 10)      # 200 EUR a PMC 20
    assert pf.holdings["A"] == pytest.approx(20.0)
    assert pf.pmc["A"] == pytest.approx(15.0)
    assert pf.assets_costs["A"] == pytest.approx(300.0)


def test_la_commissione_di_acquisto_e_sul_controvalore():
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01)
    assert pf.buy(10.0, "A", 10) == pytest.approx(1.0)   # 100 EUR * 1%


def test_vendita_in_plusvalenza_tassa_il_solo_guadagno():
    pf = nuovo_portafoglio({"A": 10.0}, tax=0.26)
    pf.buy(10.0, "A", 100)
    fee, tax = pf.sell(20.0, "A", 50)
    assert fee == pytest.approx(0.0)
    assert tax == pytest.approx(50 * (20.0 - 10.0) * 0.26)      # 130
    assert pf.holdings["A"] == pytest.approx(50.0)
    assert pf.assets_costs["A"] == pytest.approx(500.0)
    assert pf.pmc["A"] == pytest.approx(10.0)                   # PMC invariato


def test_vendita_in_perdita_non_genera_credito_dimposta():
    """Sulla perdita l'imposta e' zero: non esiste compensazione immediata nel motore."""
    pf = nuovo_portafoglio({"A": 20.0}, tax=0.26)
    pf.buy(20.0, "A", 100)
    _, tax = pf.sell(10.0, "A", 100)
    assert tax == pytest.approx(0.0)


def test_vendita_oltre_le_quote_detenute_solleva_errore():
    pf = nuovo_portafoglio({"A": 10.0})
    pf.buy(10.0, "A", 100)
    with pytest.raises(ValueError, match="Cannot sell more than held"):
        pf.sell(10.0, "A", 101)


def test_vendita_entro_la_tolleranza_viene_limitata_alle_quote():
    """Fino a holdings*1.0001 la quantita' e' tagliata invece di sollevare: e' la
    tolleranza che evita di fallire per errori di arrotondamento."""
    pf = nuovo_portafoglio({"A": 10.0})
    pf.buy(10.0, "A", 100)
    pf.sell(10.0, "A", 100 * 1.00005)
    assert pf.holdings["A"] == pytest.approx(0.0, abs=1e-9)


def test_trade_negativo_vende_positivo_compra():
    pf = nuovo_portafoglio({"A": 10.0})
    pf.prices = pd.Series({"A": 10.0})
    pf.trade("A", 10)
    assert pf.holdings["A"] == pytest.approx(10.0)
    costi, imposte = pf.trade("A", -4)
    assert pf.holdings["A"] == pytest.approx(6.0)
    assert imposte == pytest.approx(0.0)      # vendita al PMC: nessun guadagno


# --- costi di detenzione e di uscita -------------------------------------

def test_i_costi_di_detenzione_non_cambiano_il_pmc():
    """Quote e costo di carico si riducono dello stesso fattore."""
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0}), 1000, {"A": 1.0}, 0.0, 0.002)
    pmc_prima, quote_prima = pf.pmc["A"], pf.holdings["A"]
    pf.apply_holding_costs()
    assert pf.pmc["A"] == pytest.approx(pmc_prima)
    assert pf.holdings["A"] < quote_prima


def test_cash_out_costs_non_modifica_il_portafoglio():
    pf = nuovo_portafoglio({"A": 10.0}, tax=0.26)
    pf.buy(10.0, "A", 100)
    pf.prices = pd.Series({"A": 20.0})
    quote, costi = pf.holdings.copy(), pf.assets_costs.copy()
    pf.cash_out_costs()
    assert pf.holdings.equals(quote)
    assert pf.assets_costs.equals(costi)


def test_cash_out_costs_somma_commissioni_e_imposte():
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01, tax=0.26)
    pf.buy(10.0, "A", 100)                     # costo 1000, commissione d'ingresso 10
    pf.prices = pd.Series({"A": 20.0})         # controvalore 2000
    uscita = pf.cash_out_costs()
    # PMC 10,10 (la commissione d'ingresso fa parte del costo di carico): guadagno 990.
    # La commissione d'uscita (20) riduce il corrispettivo: base imponibile 970, imposta
    # 252,20. Totale 20 + 252,20. Prima del #87 erano 20 + 260 = 280, con il guadagno
    # calcolato senza togliere le due commissioni.
    assert uscita["A"] == pytest.approx(20.0 + 0.26 * (1000 - 10 - 20))   # 20 + 252,20 = 272,20


def test_cash_out_costs_con_aliquota_zero_sono_solo_commissioni():
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01, tax=0.0)
    pf.buy(10.0, "A", 100)
    pf.prices = pd.Series({"A": 20.0})
    assert pf.cash_out_costs()["A"] == pytest.approx(20.0)


def test_weights_su_portafoglio_azzerato_non_divide_per_zero():
    pf = nuovo_portafoglio({"A": 10.0})
    assert (pf.weights == 0.0).all()


# --- ribilanciamento -----------------------------------------------------

def test_rebalancer_sotto_soglia_non_tocca_nulla():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 10.4, "B": 10.0})     # A al 51%: delta 1%
    quote = pf.holdings.copy()
    costi, imposte, trades = Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.05,
                                        tax_rate=0.0).rebalance(pf)
    assert all(v == 0.0 for v in trades.values())
    assert all(v == 0.0 for v in costi.values())
    assert all(v == 0.0 for v in imposte.values())
    assert pf.holdings.equals(quote)


def test_rebalancer_sopra_soglia_riporta_ai_pesi_target():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 20.0, "B": 10.0})     # A raddoppiato: 80/20
    Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.01, tax_rate=0.0).rebalance(pf)
    assert pf.weights["A"] == pytest.approx(0.5)
    assert pf.weights["B"] == pytest.approx(0.5)


def test_rebalancer_conserva_il_valore_al_netto_di_costi_e_imposte():
    """Vendite e acquisti spostano valore, non lo creano: il calo del portafoglio
    deve coincidere con commissioni piu' imposte."""
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 20.0, "B": 10.0})
    valore_prima = pf.broker_assets_value
    costi, imposte, _ = Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.01,
                                   tax_rate=0.26).rebalance(pf)
    delta = sum(costi.values()) + sum(imposte.values())
    assert pf.broker_assets_value == pytest.approx(valore_prima + delta)


def test_rebalancer_paga_limposta_solo_sullasset_venduto_in_guadagno():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    pf.prices = pd.Series({"A": 20.0, "B": 10.0})
    _, imposte, _ = Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.01,
                               tax_rate=0.26).rebalance(pf)
    assert imposte["A"] < 0.0        # A e' in guadagno: vendita tassata
    assert imposte["B"] == pytest.approx(0.0)   # B e' al PMC: nessuna imposta


def test_rebalancer_a_target_esatto_non_genera_trade():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 10.0, "B": 10.0}), 1000,
                                   {"A": 0.5, "B": 0.5}, 0.0, 0.0)
    _, _, trades = Rebalancer(pd.Series({"A": 0.5, "B": 0.5}), 0.0,
                              tax_rate=0.0).rebalance(pf)
    assert all(abs(v) < 1e-9 for v in trades.values())


# --- commissioni e prezzo di carico (issue #87) ---------------------------

def test_il_prezzo_di_carico_comprende_la_commissione_di_acquisto():
    """100 quote a 10 con commissione 1%: si pagano 1.010, non 1.000, quindi PMC 10,10."""
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01, tax=0.26)
    fee = pf.buy(10.0, "A", 100)
    assert fee == pytest.approx(10.0)
    assert pf.assets_costs["A"] == pytest.approx(1010.0)      # 1000 + 10 di commissione
    assert pf.pmc["A"] == pytest.approx(10.10)


def test_vendere_al_prezzo_di_acquisto_non_genera_plusvalenza():
    """Comprato e rivenduto allo stesso prezzo non c'e' guadagno: nemmeno con le commissioni."""
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01, tax=0.26)
    pf.buy(10.0, "A", 100)
    _, imposta = pf.sell(10.0, "A", 100)
    assert imposta == pytest.approx(0.0)


def test_la_commissione_di_vendita_riduce_il_corrispettivo():
    """Prezzo da 10 a 12 con fee 1%: base imponibile 200 - 12, non 200."""
    pf = nuovo_portafoglio({"A": 10.0}, fee=0.01, tax=0.26)
    pf.buy(10.0, "A", 100)                       # PMC 10,10
    _, imposta = pf.sell(12.0, "A", 100)
    imponibile = 100 * (12.0 - 10.10) - 100 * 12.0 * 0.01     # 190 - 12 = 178
    assert imposta == pytest.approx(0.26 * imponibile)        # 46,28

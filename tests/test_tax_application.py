import pandas as pd
from classes import portfolio_evo


def make_df():
    # minimal dataframe with single asset to instantiate portfolio
    df = pd.DataFrame({
        'Date': ['01/01/2025','02/01/2025'],
        'A': [100.0, 110.0]
    })
    return df


def test_tax_behavior_sale_vs_gain():
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.26,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False)

    # Set up a simple state: one asset 'A'
    ptf.IndexName = ['A']
    ptf.notional = pd.Series({'A': 10.0})
    ptf.PMC = pd.Series({'A': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0})

    # Case 1: we sell 1 unit at price > PMC (realized gain)
    ptf.delta_notional = pd.Series({'A': -1.0})
    StockPrice = pd.Series({'A': 120.0})
    ptf.update_tax(StockPrice)

    # Expected: tax applied only on realized gains = -(delta * (price - PMC)) * tax_rate
    expected_gain_based = - (ptf.delta_notional * (StockPrice - ptf.PMC)).sum() * ptf.tax_rate

    assert ptf.tax == expected_gain_based

    # Case 2: sell when price < PMC -> no tax should be applied
    ptf.delta_notional = pd.Series({'A': -1.0})
    StockPrice2 = pd.Series({'A': 90.0})
    ptf.update_tax(StockPrice2)
    assert ptf.tax == 0.0


def test_tax_sum_multiple_assets():
    # multiple assets sold with price > PMC should sum taxes across assets
    df = pd.DataFrame({
        'Date': ['01/01/2025'],
        'A': [100.0],
        'B': [200.0]
    })
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.30,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[0.5, 0.5],
                        imported_dataframe=df,
                        stock_price_normalization=False)

    ptf.IndexName = ['A', 'B']
    ptf.notional = pd.Series({'A': 10.0, 'B': 5.0})
    ptf.PMC = pd.Series({'A': 100.0, 'B': 200.0})
    ptf.PMC_weight = pd.Series({'A': 1.0, 'B': 1.0})

    # sell 1 unit of A and 2 units of B at prices above PMC
    ptf.delta_notional = pd.Series({'A': -1.0, 'B': -2.0})
    StockPrice = pd.Series({'A': 120.0, 'B': 250.0})
    ptf.update_tax(StockPrice)

    expected = - (ptf.delta_notional * (StockPrice - ptf.PMC)).sum() * ptf.tax_rate
    assert ptf.tax == expected


def test_update_notional_tax_transaccost_immediate_payments():
    # integration test: calling update_notional_tax_transaccost should
    # compute tax and add it to immediate_payments (transactional_cost_rate = 0)
    df = pd.DataFrame({
        'Date': ['01/01/2025'],
        'A': [100.0],
        'B': [100.0]
    })
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.20,
                        exp_rate=0.0,
                        rebalance_threshold=0.0,
                        initial_w=[0.0, 1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False)

    # prepare internal state to force a sale on asset A (initial_w - w < 0)
    ptf.IndexName = ['A', 'B']
    ptf.notional = pd.Series({'A': 10.0, 'B': 10.0})
    ptf.PMC = pd.Series({'A': 100.0, 'B': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0, 'B': 1.0})
    # current weights set to 50/50 so target [0.0,1.0] implies selling A
    ptf.w = pd.Series({'A': 0.5, 'B': 0.5})

    StockPrice = pd.Series({'A': 120.0, 'B': 100.0})

    # ensure starting immediate payments is zero
    ptf.immediate_payments = 0.0

    ptf.update_notional_tax_transaccost(StockPrice)

    # expected tax computed by implementation
    mask_tax = (ptf.delta_notional < 0) & (StockPrice > ptf.PMC)
    expected_tax = - (ptf.delta_notional * (StockPrice - ptf.PMC))[mask_tax].sum() * ptf.tax_rate if mask_tax.any() else 0.0

    # transactional cost rate = 0 so immediate_payments should equal tax
    assert ptf.tax == expected_tax
    assert ptf.immediate_payments == ptf.tax


# ── Riporto minusvalenze (zainetto fiscale) ─────────────────────────────────

def test_loss_carryforward_offsets_gain():
    """Minusvalenza realizzata nell'anno Y compensa plusvalenza nell'anno Y+1."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.26,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False,
                        calcola_minusvalenze=True)
    ptf.IndexName = ['A']
    ptf.PMC = pd.Series({'A': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0})

    # Vendita in perdita 2022: -((-1)*(80-100)) = -20 → minusvalenza 20
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 80.0}), current_date=pd.Timestamp('2022-06-15'))
    assert ptf.tax == 0.0
    assert ptf.loss_carryforward == {2022: 20.0}

    # Vendita in guadagno 2023: plusvalenza 15 < credito 20 → nessuna tassa
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 115.0}), current_date=pd.Timestamp('2023-03-01'))
    assert ptf.tax == 0.0
    assert abs(ptf.loss_carryforward.get(2022, 0.0) - 5.0) < 1e-9  # credito residuo


def test_loss_carryforward_partial_offset():
    """Plusvalenza superiore al carry-forward: tassa solo sul netto."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.26,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False,
                        calcola_minusvalenze=True)
    ptf.IndexName = ['A']
    ptf.PMC = pd.Series({'A': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0})

    # Credito da perdita: 30 (prezzo 70 < PMC 100)
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 70.0}), current_date=pd.Timestamp('2021-01-01'))
    assert ptf.loss_carryforward == {2021: 30.0}

    # Guadagno 50, offset con 30 → tassa sul netto 20
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 150.0}), current_date=pd.Timestamp('2022-01-01'))
    expected_tax = 20.0 * 0.26
    assert abs(ptf.tax - expected_tax) < 1e-9
    assert len(ptf.loss_carryforward) == 0  # carry-forward esaurito


def test_loss_carryforward_expiry():
    """Minusvalenza scade dopo 4 anni (art. 68 TUIR)."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.26,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False,
                        calcola_minusvalenze=True)
    ptf.IndexName = ['A']
    ptf.PMC = pd.Series({'A': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0})

    # Perdita anno 2019: minusvalenza 40
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 60.0}), current_date=pd.Timestamp('2019-06-01'))
    assert 2019 in ptf.loss_carryforward

    # Guadagno anno 2024 (5 anni dopo) → credito 2019 scaduto, tassa piena
    ptf.delta_notional = pd.Series({'A': -1.0})
    ptf.update_tax(pd.Series({'A': 140.0}), current_date=pd.Timestamp('2024-06-01'))
    expected_tax = 40.0 * 0.26
    assert abs(ptf.tax - expected_tax) < 1e-9


def test_intra_rebalance_netting():
    """Perdita e guadagno nella stessa operazione si compensano prima del carry-forward."""
    df = pd.DataFrame({'Date': ['01/01/2025'], 'A': [100.0], 'B': [100.0]})
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.26,
                        exp_rate=0.0,
                        rebalance_threshold=1.0,
                        initial_w=[0.5, 0.5],
                        imported_dataframe=df,
                        stock_price_normalization=False)
    ptf.IndexName = ['A', 'B']
    ptf.PMC = pd.Series({'A': 100.0, 'B': 100.0})
    ptf.PMC_weight = pd.Series({'A': 1.0, 'B': 1.0})

    # Vendo 1 A con guadagno 20, vendo 1 B con perdita 20 → netto 0, no tassa
    ptf.delta_notional = pd.Series({'A': -1.0, 'B': -1.0})
    ptf.update_tax(pd.Series({'A': 120.0, 'B': 80.0}), current_date=pd.Timestamp('2025-01-01'))
    assert ptf.tax == 0.0
    assert len(ptf.loss_carryforward) == 0  # niente da portare avanti


# ── Spese ricorrenti (exp_rate / imposta di bollo) ──────────────────────────

def test_exp_cost_zero_on_first_call():
    """La prima chiamata a update_exp_cost inizializza la data senza addebitare."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.0,
                        exp_rate=0.01,
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False)
    ptf.notional = pd.Series({'A': 10.0})
    StockPrice = pd.Series({'A': 100.0})

    ptf.update_exp_cost(pd.Timestamp('2025-01-01'), StockPrice)
    assert ptf.exp_cost == 0.0
    assert ptf.immediate_payments == 0.0


def test_exp_cost_applied_proportionally():
    """update_exp_cost addebita exp_rate * gross * (giorni/365.25)."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.0,
                        exp_rate=0.01,  # 1% annuo
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False)
    ptf.notional = pd.Series({'A': 10.0})
    StockPrice = pd.Series({'A': 100.0})
    gross = 1000.0

    ptf.update_exp_cost(pd.Timestamp('2025-01-01'), StockPrice)  # inizializza
    ptf.update_exp_cost(pd.Timestamp('2026-01-01'), StockPrice)  # 365 giorni dopo
    expected = -gross * 0.01 * (365 / 365.25)
    assert abs(ptf.exp_cost - expected) < 1e-6
    assert abs(ptf.immediate_payments - expected) < 1e-6


def test_exp_cost_accumulates_over_multiple_calls():
    """Chiamate successive accumulano il costo in immediate_payments."""
    df = make_df()
    ptf = portfolio_evo(initial_balance=1000.0,
                        transac_cost_rate=0.0,
                        tax_rate=0.0,
                        exp_rate=0.002,  # 0.2% annuo (bollo)
                        rebalance_threshold=1.0,
                        initial_w=[1.0],
                        imported_dataframe=df,
                        stock_price_normalization=False)
    ptf.notional = pd.Series({'A': 10.0})
    StockPrice = pd.Series({'A': 100.0})

    ptf.update_exp_cost(pd.Timestamp('2025-01-01'), StockPrice)
    ptf.update_exp_cost(pd.Timestamp('2025-07-01'), StockPrice)  # 181 giorni
    ptf.update_exp_cost(pd.Timestamp('2026-01-01'), StockPrice)  # altri 184 giorni
    # immediate_payments deve essere negativo (cumulo costi)
    assert ptf.immediate_payments < 0.0
    # totale ≈ -1000 * 0.002 * 365/365.25 (la somma dei due step è quasi un anno)
    expected_full_year = -1000.0 * 0.002 * (365 / 365.25)
    assert abs(ptf.immediate_payments - expected_full_year) < 1e-6

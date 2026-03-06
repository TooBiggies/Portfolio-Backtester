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

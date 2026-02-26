import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

# ==========================================
# IMPORT ACTUAL MODULES
# ==========================================
from engine import Portfolio, Rebalancer, PortfolioTracker
from classes import portfolio_evo


# ==========================================
# TEST CONFIGURATION
# ==========================================
CONFIG = {
    'initial_balance': 1000.0,
    'transac_cost_rate': 0.,#0.0029,  # 0.19% commission + 0.1% spread
    'exp_rate': 0.,#0.002,            # 0.2% imposta di bollo
    'tax_rate': 0,#.26,             # 26% capital gains tax
    'rebalance_threshold': 0.1,   # 10% drift trigger
    'start_date': "2000-01-03",
    'end_date': "2025-09-04",
}

# Allocazione di reference:
# Index 1  # Index 2 # Index 3 # Index 4 ...
#                 VTSIM SPYSIM  VXUSSIM GLDSIM  CASHX SHYSIM  IEFSIM  TLTSIM  ZROZSIM KMLMSIM DBMFSIM

INITIAL_WEIGHTS = [ 0.5,  0,      0,      0.5,   0,    0,      0,      0,      0.,   0.,   0.]


# ==========================================
# OLD SIMULATION (portfolio_evo from classes.py)
# ==========================================
def run_old_simulation(df, initial_w, params):
    """Run simulation using old portfolio_evo class"""
    ptf = portfolio_evo(
        initial_balance=params['initial_balance'],
        transac_cost_rate=params['transac_cost_rate'],
        tax_rate=params['tax_rate'],
        exp_rate=params['exp_rate'],
        rebalance_threshold=params['rebalance_threshold'],
        initial_w=initial_w,
        imported_dataframe=df,
        stock_price_normalization=True
    )

    df_log = pd.DataFrame(index=ptf.date)

    for i in ptf.StockPrice.index:
        ptf.reset_tax_transaccost()
        ptf.reset_delta_notional()
        
        StockPrice = ptf.StockPrice.loc[i, :]
        ptf.update_AssetValue_weight(StockPrice)
        
        if ptf.check_rebalance():
            ptf.update_notional_tax_transaccost(StockPrice)

        ptf.update_Return(StockPrice)    
        ptf.update_TotValue(StockPrice)    
        ptf.update_NetTotValue(StockPrice)

        df_log.loc[ptf.date[i], "TotValue"] = ptf.TotValue
        df_log.loc[ptf.date[i], "NetTotValue"] = ptf.NetTotValue
        df_log.loc[ptf.date[i], "Taxes"] = ptf.tax
        df_log.loc[ptf.date[i], "TransacCost"] = ptf.TransactionalCost
        
    return df_log


# ==========================================
# NEW SIMULATION (Portfolio from engine.py)
# ==========================================
def run_new_simulation(df, initial_w, params):
    """Run simulation using new Portfolio + Rebalancer + PortfolioTracker classes"""
    index_name = [col for col in df.columns if col != "Date"]
    prices_df = df.loc[:, index_name] / df.loc[0, index_name]  # Normalize like old code
    dates = pd.to_datetime(df['Date'], format='%d/%m/%Y')
    
    # Initialize Portfolio
    ptf = Portfolio(
        prices=prices_df.loc[0, :], 
        initial_value=params['initial_balance'],
        brokerage_fee_rate=params['transac_cost_rate']
    )
    
    # Initialize Rebalancer
    rebalancer = Rebalancer(
        target_weights=pd.Series(initial_w, index=index_name), 
        threshold=params['rebalance_threshold'],
        tax_rate=params['tax_rate']
    )
    
    # Initialize Tracker (computes daily deltas from cumulative values)
    tracker = PortfolioTracker()
    
    # Initial allocation (Day 0) - match old code's fully invested start
    for asset in index_name:
        w = initial_w[index_name.index(asset)]
        target_val = w * params['initial_balance']
        price = prices_df.loc[0, asset]
        units = target_val / price
        ptf.buy(price, asset, units)
    
    # Simulation loop
    for i, row in prices_df.iterrows():
        ptf.prices = row
        taxes, costs = rebalancer.rebalance(ptf)
        tracker.update(ptf, dates[i], taxes, costs)

    return tracker.to_dataframe()


# ==========================================
# DATA LOADING
# ==========================================
def load_data():
    return pd.read_csv("./Timeseries.csv", sep=";")


def preprocess_data(df):
    """Preprocess dataframe to match old code expectations"""
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df[(df["Date"] >= pd.to_datetime(CONFIG['start_date']))].copy()
    df = df[(df["Date"] <= pd.to_datetime(CONFIG['end_date']))].copy()
    df = df.reset_index(drop=True)
    return df


# ==========================================
# TEST COMPARISON
# ==========================================
def compare_results(df_old, df_new):
    """Compare old vs new simulation results"""
    print("\n" + "="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    
    tests = [
        ("TotValue", "Gross Value", 1e-2),
        ("NetTotValue", "Net Value", 1e-2),
        ("Taxes", "Daily Taxes", 1e-3),
        ("TransacCost", "Daily Costs", 1e-3),
    ]
    
    results = {}
    for col, name, atol in tests:
        try:
            pd.testing.assert_series_equal(
                df_old[col], df_new[col], 
                check_names=False, atol=atol
            )
            print(f"[PASS] {name:15s} ✓")
            results[col] = True
        except AssertionError as e:
            diff = df_old[col] - df_new[col]
            idx = diff.abs().idxmax()
            max_diff = diff.abs().max()
            print(f"[FAIL] {name:15s} max diff {max_diff:>12.6f} at {idx}")
            results[col] = False
    
    print("="*70)
    
    # Summary
    passed = sum(results.values())
    total = len(results)
    print(f"Summary: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! New implementation matches old code.")
    else:
        print("⚠ Some tests failed. Review differences above.")
    
    return results


# ==========================================
# PLOTTING
# ==========================================
def plot_comparison(df_old, df_new):
    """Generate comparison plots"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    plots = [
        ("TotValue", "Gross Value (TotValue)", "€"),
        ("NetTotValue", "Net Value (NetTotValue)", "€"),
        ("Taxes", "Daily Taxes", "€"),
        ("TransacCost", "Daily Transaction Costs", "€"),
    ]
    
    for ax, (col, title, unit) in zip(axes.flat, plots):
        ax.plot(df_old.index, df_old[col], label="Old (classes.py)", alpha=0.7, linewidth=1)
        ax.plot(df_new.index, df_new[col], label="New (engine.py)", alpha=0.7, linestyle='--', linewidth=1)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel("Date")
        ax.set_ylabel(unit)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)
        ax.ticklabel_format(style='plain', axis='y')
    
    plt.tight_layout()
    plt.savefig("portfolio_comparison.png", dpi=150, bbox_inches='tight')
    print("\n✓ Plot saved to portfolio_comparison.png")
    
    # Also save difference plot
    fig2, ax2 = plt.subplots(4, 1, figsize=(16, 12))
    for ax, (col, title, _) in zip(ax2.flat, plots):
        diff = df_old[col] - df_new[col]
        ax.plot(diff.index, diff, color='red', alpha=0.7, linewidth=0.5)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_title(f"Difference: Old - New ({title})")
        ax.set_xlabel("Date")
        ax.set_ylabel("€")
        ax.grid(True, alpha=0.3)
        ax.ticklabel_format(style='plain', axis='y')
    
    plt.tight_layout()
    plt.savefig("portfolio_difference.png", dpi=150, bbox_inches='tight')
    print("✓ Difference plot saved to portfolio_difference.png")


# ==========================================
# MAIN
# ==========================================
def main():
    print("="*70)
    print("PORTFOLIO SIMULATION TEST")
    print("Comparing engine.py (new) vs classes.py (old)")
    print("="*70)
    
    # Load data
    df_raw = load_data()
    df = preprocess_data(df_raw)
    print(f"✓ Data range: {df['Date'].min()} to {df['Date'].max()}")
    print(f"✓ Number of days: {len(df)}")
    print(f"✓ Assets: {[c for c in df.columns if c != 'Date'][:5]}...")
    
    # Run simulations
    print("\nRunning old simulation (classes.py)...")
    df_old = run_old_simulation(df, INITIAL_WEIGHTS, CONFIG)
    print(f"✓ Old simulation complete: {len(df_old)} days")
    
    print("\nRunning new simulation (engine.py)...")
    df_new = run_new_simulation(df, INITIAL_WEIGHTS, CONFIG)
    print(f"✓ New simulation complete: {len(df_new)} days")
    
    # Align indices
    df_new.index = df_old.index
    
    # Compare results
    results = compare_results(df_old, df_new)
    
    # Generate plots
    plot_comparison(df_old, df_new)
    
    # Save detailed CSV for manual inspection
    df_old.to_csv("test_output_old.csv")
    df_new.to_csv("test_output_new.csv")
    print("✓ Detailed output saved to test_output_old.csv and test_output_new.csv")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    
    return results


if __name__ == "__main__":
    results = main()
    # Exit with error code if tests failed
    exit(0 if all(results.values()) else 1)
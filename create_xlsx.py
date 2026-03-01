import pandas as pd
import numpy as np
from engine import *

# =============================================================================
# EVOLUTION LOOP - Creates both DataFrames
# =============================================================================

def run_portfolio_evolution(df_prices: pd.DataFrame, 
                            initial_value: float,
                            initial_weights: dict,
                            rebalance_threshold: float,
                            tax_rate: float = 0.26,
                            brokerage_fee_rate: float = 0.0,
                            asset_columns: list = None):
    """
    Runs the portfolio evolution through time and returns df_log and df_log_delta.
    
    Parameters:
    -----------
    df_prices : pd.DataFrame
        Historical prices with Date as index and assets as columns
    initial_value : float
        Starting portfolio value
    initial_weights : dict
        Target weights for each asset (must sum to 1)
    rebalance_threshold : float
        Threshold for triggering rebalance (e.g., 0.05 for 5% drift)
    tax_rate : float
        Capital gains tax rate
    brokerage_fee_rate : float
        Transaction cost rate
    asset_columns : list
        Exact column order for output (matches Excel headers)
    
    Returns:
    --------
    df_log : pd.DataFrame
        Daily portfolio metrics and asset values
    df_log_delta : pd.DataFrame
        Daily trade deltas (monetary value per asset)
    """
    
    if asset_columns is None:
        asset_columns = ['VTSIM', 'SPYSIM', 'VXUSSIM', 'GLDSIM', 'CASHX', 
                         'SHYSIM', 'IEFSIM', 'TLTSIM', 'ZROZSIM', 'KMLMSIM', 'DBMFSIM']
    
    # Initialize tracker
    tracker = PortfolioTracker(asset_columns=asset_columns)
    rebalancer = Rebalancer(target_weights=pd.Series(initial_weights), 
                           threshold=rebalance_threshold, 
                           tax_rate=tax_rate)
    
    # Cumulative costs (to match original ptf.tax and ptf.TransactionalCost behavior)
    cumulative_tax = 0.0
    cumulative_cost = 0.0
    
    dates = df_prices.index
    n_days = len(dates)
    
    # =============================================================================
    # T=0: INITIAL STATE (no trades yet)
    # =============================================================================
    initial_prices = df_prices.iloc[0]
    portfolio = Portfolio(prices=initial_prices, 
                         initial_value=initial_value, 
                         brokerage_fee_rate=brokerage_fee_rate)
    
    # Initialize holdings based on initial weights
    for asset, weight in initial_weights.items():
        if asset in portfolio.assets and weight > 0:
            units = (initial_value * weight) / initial_prices[asset]
            portfolio.buy(initial_prices[asset], asset, units)
    
    # Log initial state (t=0)
    tracker.update(portfolio, 
                   date=dates[0], 
                   taxes=0.0, 
                   costs=0.0, 
                   trade_deltas={col: 0.0 for col in asset_columns})
    
    # =============================================================================
    # T=1 to N: EVOLUTION LOOP
    # =============================================================================
    for i in range(1, n_days):
        # 1. Update prices
        current_prices = df_prices.iloc[i]
        portfolio.prices = current_prices
        
        # 2. Check and execute rebalance
        tax, cost, trade_deltas = rebalancer.rebalance(portfolio)
        
        # 3. Accumulate cumulative costs (match original ptf.tax behavior)
        cumulative_tax += tax
        cumulative_cost += cost
        
        # 4. Log state
        tracker.update(portfolio, 
                       date=dates[i], 
                       taxes=cumulative_tax, 
                       costs=cumulative_cost, 
                       trade_deltas=trade_deltas)
    
    # =============================================================================
    # RETURN DATAFRAMES
    # =============================================================================
    df_log, df_log_delta = tracker.to_dataframes()
    
    return df_log, df_log_delta


# =============================================================================
# HELPER: Prepare Price DataFrame from Loaded CSV
# =============================================================================

def load_data():
    return pd.read_csv("./Timeseries.csv", sep=";")


def preprocess_data(df):
    """Preprocess dataframe to match old code expectations"""
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.reset_index(drop=True)
    return df


def prepare_price_dataframe(df_raw, asset_columns=None, date_column='Date'):
    """
    Convert loaded CSV into price DataFrame with Date as index.
    
    Parameters:
    -----------
    df_raw : pd.DataFrame
        Output from load_data() + preprocess_data()
    asset_columns : list
        Which columns to use as asset prices (exclude Date, etc.)
    date_column : str
        Name of the date column
    
    Returns:
    --------
    df_prices : pd.DataFrame
        DataFrame with Date as index and assets as columns
    """
    df = df_raw.copy()
    
    if asset_columns is None:
        # Auto-detect: exclude Date column
        asset_columns = [col for col in df.columns if col != date_column]
    
    # Set Date as index
    df_prices = df.set_index(date_column)[asset_columns]
    
    return df_prices


# =============================================================================
# EXAMPLE USAGE (Complete Pipeline)
# =============================================================================

if __name__ == "__main__":
    # 1. LOAD DATA
    df_raw = load_data()
    df_raw = preprocess_data(df_raw)
    
    print(f"Loaded {len(df_raw)} rows")
    print(f"Columns: {list(df_raw.columns)}")
    print(f"Date range: {df_raw['Date'].min()} to {df_raw['Date'].max()}")
    
    # 2. DEFINE ASSET COLUMNS (Match your Excel headers)
    # Adjust based on what's actually in your Timeseries.csv
    asset_columns = ['VTSIM', 'SPYSIM', 'VXUSSIM', 'GLDSIM', 'CASHX', 
                     'SHYSIM', 'IEFSIM', 'TLTSIM', 'ZROZSIM', 'KMLMSIM', 'DBMFSIM']
    
    # Filter to only columns that exist in your data
    available_columns = [col for col in asset_columns if col in df_raw.columns]
    print(f"\nUsing {len(available_columns)} assets: {available_columns}")
    
    # 3. PREPARE PRICE DATAFRAME
    df_prices = prepare_price_dataframe(df_raw, asset_columns=available_columns)
    
    # Initial allocation (must sum to 1)
    initial_weights = {
        'VTSIM': 0.50,
        'SPYSIM': 0.00,
        'VXUSSIM': 0.00,
        'GLDSIM': 0.00,
        'CASHX': 0.50,  # Cash as liquidity
        'SHYSIM': 0.00,
        'IEFSIM': 0.00,
        'TLTSIM': 0.00,
        'ZROZSIM': 0.00,
        'KMLMSIM': 0.00,
        'DBMFSIM': 0.00,
    }
    
    # Run evolution
    df_log, df_log_delta = run_portfolio_evolution(
        df_prices=df_prices,
        initial_value=100000,
        initial_weights=initial_weights,
        rebalance_threshold=0.05,
        tax_rate=0.26,
        brokerage_fee_rate=0.001,
        asset_columns=list(initial_weights.keys())
    )
    
    # Display results
    print("=== df_log (first 5 rows) ===")
    print(df_log.head())
    print(f"\nShape: {df_log.shape}")
    print(f"Columns: {list(df_log.columns)}")
    
    print("\n=== df_log_delta (first 5 rows) ===")
    print(df_log_delta.head())
    print(f"\nShape: {df_log_delta.shape}")
    
    #Export to Excel (matching original format)
    df_log.to_excel("new_portfolio_log.xlsx")
    df_log_delta.to_excel("new_portfolio_delta_log.xlsx")
import numpy as np
import pandas as pd
import os
import sys
import matplotlib.pyplot as plt

from engine import *


def load_data():
    return pd.read_csv("./Timeseries.csv", sep=";")



def preprocess_data(df, begin_date="2020-01-02", end_date="2026-01-20"):
    """Preprocess dataframe to match old code expectations"""
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df[(df["Date"]>=pd.to_datetime(begin_date))].copy()
    df = df[(df["Date"]<=pd.to_datetime(end_date))].copy()
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


def backtest(initial_value, begin_date, end_date, weights, brokerage_fee_rate=0.0029, rebalance_threshold=0.1, tax_rate=0.26):

    asset_columns=list(weights.keys())
    prices = prepare_price_dataframe(preprocess_data(load_data(), begin_date=begin_date, end_date=end_date), asset_columns=asset_columns)
    dates = prices.index
    initial_prices = prices.iloc[0]

    # Initialize tracker and rebalancer 
    tracker = PortfolioTracker(asset_columns=asset_columns, begin_date=begin_date)
    rebalancer = Rebalancer(target_weights=pd.Series(weights), threshold=rebalance_threshold, tax_rate=tax_rate)

    # Create and fund the portfolio in one step
    portfolio, fees = Portfolio.from_weights(prices=initial_prices, value=initial_value, weights=weights, brokerage_fee_rate=brokerage_fee_rate, annual_costs_rate=0.002)

    # Log initial state (t=0)
    tracker.update(portfolio, date=dates[0], taxes=0.0, costs=fees, trade_deltas={col: 0.0 for col in asset_columns})

    for i in range(1, len(dates)):
        # 1. Update prices
        portfolio.prices = prices.iloc[i]
        
        # 2. Check and execute rebalance
        tax, cost, trade_deltas = rebalancer.rebalance(portfolio)
        
        # 3. Log state
        tracker.update(portfolio, date=dates[i], taxes=tax, costs=cost, trade_deltas=trade_deltas)
    
    df_log, df_log_delta = tracker.to_dataframes()

    df_log.to_excel("output_ptf.xlsx")
    df_log_delta.to_excel("output_ptf_delta.xlsx")

    print(f"Orizzonte temporale   {begin_date} / {end_date}")
    print(f"Anni in simulazione   {round( ((pd.to_datetime(end_date) - pd.to_datetime(begin_date)).days / 365.25), 2)}")
    print(f"CAGR                  {(tracker.compound_factor**(1/(round( ((pd.to_datetime(end_date) - pd.to_datetime(begin_date)).days / 365.25), 2))) -1) * 100:.2f}%")
    print(f"Total compound return {tracker.compound_factor * 100:.2f}%")
    print(f"Capitale iniziale {initial_value}") #20260131 vincemauro
    print(f"Capitale finale {portfolio.value:.2f}") #20260131 vincemauro
    plt.semilogy(df_log.index,df_log['Compound Return'])
    plt.xlabel('Data')
    plt.ylabel('Compound Return %')
    #plt.title('Grafico')
    #plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('plot.png')


if __name__ == '__main__':

    weights = {
        'VTSIM': 0.60,
        'SPYSIM': 0.00,
        'VXUSSIM': 0.00,
        'GLDSIM': 0.10,
        'CASHX': 0.00,  # Cash as liquidity
        'SHYSIM': 0.00,
        'IEFSIM': 0.00,
        'TLTSIM': 0.00,
        'ZROZSIM': 0.25,
        'KMLMSIM': 0.00,
        'DBMFSIM': 0.05,
    }
    
    backtest(initial_value=10000,
         begin_date = pd.to_datetime("2020-01-02"), 
         end_date = pd.to_datetime("2025-09-01"), 
         weights=weights, 
         brokerage_fee_rate=0.0029, 
         rebalance_threshold=0.1, 
         tax_rate=0.26
         )

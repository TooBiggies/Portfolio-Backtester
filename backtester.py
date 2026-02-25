import sys
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import logging
import os

from classes import portfolio_evo
import backtester_config as cfg
import backtester_generate_reports as rpt


def run_backtest():
    # Load timeseries (same logic as notebook)
    imported_dataframe = pd.read_csv("./Timeseries.csv", sep=';')
    imported_dataframe["Date"] = pd.to_datetime(imported_dataframe["Date"], dayfirst=True, errors="coerce")
    imported_dataframe = imported_dataframe[(imported_dataframe["Date"]>=pd.to_datetime("2000-01-03"))].copy()
    imported_dataframe = imported_dataframe[(imported_dataframe["Date"]<=pd.to_datetime("2025-09-04"))].copy().reset_index(drop=True)

    # Prepare inputs from config
    initial_balance = cfg.CAPITAL
    start_date = cfg.START_DATE
    end_date = cfg.END_DATE
    initial_w = cfg.INITIAL_WEIGHTS

    if abs(sum(initial_w) - 1.0) > 1e-9:
        print("Warning: weights do not sum to 1. They will be normalized.")
        total = sum(initial_w)
        if total == 0:
            print("All weights zero — exiting")
            sys.exit(1)
        initial_w = [w/total for w in initial_w]

    ptf = portfolio_evo(initial_balance = initial_balance,
                        transac_cost_rate= cfg.TRANSAC_COST_RATE,
                        exp_rate=cfg.EXP_RATE,
                        tax_rate = cfg.TAX_RATE,
                        rebalance_threshold = cfg.REBALANCE_THRESHOLD,
                        initial_w = initial_w,
                        imported_dataframe= imported_dataframe,
                        start_date = start_date,
                        end_date = end_date,
                        stock_price_normalization= cfg.STOCK_PRICE_NORMALIZATION)

    df_log       = pd.DataFrame(index = ptf.date)
    df_log_delta = pd.DataFrame(index = ptf.date)

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

        df_log.loc[ptf.date[i], "Return"] = ptf.PercReturn
        df_log.loc[ptf.date[i], "Compound Return"] = ptf.CompoundReturn
        df_log.loc[ptf.date[i], "GrossValue"] = ptf.GrossValue
        df_log.loc[ptf.date[i], "BrokerValue"] = ptf.BrokerValue
        df_log.loc[ptf.date[i], "NetValue"] = ptf.NetValue
        df_log.loc[ptf.date[i], "Taxes"] = ptf.tax
        df_log.loc[ptf.date[i], "TransacCost"] = ptf.TransactionalCost
        df_log.loc[ptf.date[i], ptf.IndexName] = ptf.AssetValue
        df_log_delta.loc[ptf.date[i], ptf.IndexName] = ptf.delta_notional * StockPrice

    # After loop: prepare summary and write outputs once
    start_dt = min(ptf.date).date()
    end_dt = max(ptf.date).date()
    years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
    try:
        cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100 if years > 0 else float('nan')
    except Exception:
        cagr = float('nan')

    # Setup logger once
    logger = logging.getLogger('backtester')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(sh)

    # Log summary to terminal
    logger.info(f"Orizzonte temporale: {start_dt} / {end_dt}")
    logger.info(f"Anni in simulazione: {years}")
    logger.info(f"CAGR: {cagr:.2f}%")
    logger.info(f"Total compound return: {ptf.CompoundReturn * 100:.2f}%")
    logger.info(f"Capitale iniziale: {ptf.StartValue}")
    logger.info(f"Capitale finale: {ptf.TotValue:.2f}")

    # Generate and save reports (xlsx, markdown, html + css + plot)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    rpt.generate_reports(ptf, df_log, df_log_delta, cfg, ts=ts, out_dir=cfg.REPORTS_DIR)

    # Print concise summary to stdout
    print(f"Orizzonte temporale   {min(ptf.date).date()} / {max(ptf.date).date()}")
    years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
    print(f"Anni in simulazione   {years}")
    try:
        cagr = (ptf.CompoundReturn**(1/years) -1) * 100 if years>0 else float('nan')
    except Exception:
        cagr = float('nan')
    print(f"CAGR                  {cagr:.2f}%")
    print(f"Total compound return {ptf.CompoundReturn * 100:.2f}%")
    print(f"Capitale iniziale {ptf.StartValue}")
    print(f"Capitale finale {ptf.TotValue:.2f}")


if __name__ == '__main__':
    run_backtest()

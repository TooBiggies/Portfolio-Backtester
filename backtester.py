import sys
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import logging
import os

from classes import portfolio_evo
import backtester_config as cfg


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

        StockPrice = ptf.StockPrice.loc[i,:]
        ptf.update_AssetValue_weight(StockPrice)

        if ptf.check_rebalance():
            ptf.update_notional_tax_transaccost(StockPrice)

        ptf.update_Return(StockPrice)
        ptf.update_TotValue(StockPrice)
        ptf.update_NetTotValue(StockPrice)

        df_log.loc[ptf.date[i], "Return"]                = ptf.PercReturn
        df_log.loc[ptf.date[i], "Compound Return"]       = ptf.CompoundReturn
        df_log.loc[ptf.date[i], "TotValue"]              = ptf.TotValue
        df_log.loc[ptf.date[i], "Taxes"]                 = ptf.tax
        df_log.loc[ptf.date[i], "TransacCost"]           = ptf.TransactionalCost
        df_log.loc[ptf.date[i], ptf.IndexName]            = ptf.AssetValue
        df_log_delta.loc[ptf.date[i], ptf.IndexName]      = ptf.delta_notional*StockPrice

        # Save outputs (filenames from config)
        # Ensure reports dir exists and create a timestamp for this iteration
        os.makedirs(cfg.REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Save Excel outputs into the reports directory with the same timestamp
        xlsx_name = f"{ts}_{os.path.basename(cfg.OUTPUT_XLSX)}"
        delta_name = f"{ts}_{os.path.basename(cfg.OUTPUT_DELTA_XLSX)}"
        xlsx_path = os.path.join(cfg.REPORTS_DIR, xlsx_name)
        delta_path = os.path.join(cfg.REPORTS_DIR, delta_name)
        df_log.to_excel(xlsx_path)
        df_log_delta.to_excel(delta_path)

        # Prepare summary
        start_dt = min(ptf.date).date()
        end_dt = max(ptf.date).date()
        years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
        try:
            cagr = (ptf.CompoundReturn**(1/years) -1) * 100 if years>0 else float('nan')
        except Exception:
            cagr = float('nan')

        # Setup logger
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

        # Save a markdown report with timestamp inside configured reports dir
        os.makedirs(cfg.REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_name = f"{ts}_backtest_report.md"
        report_path = os.path.join(cfg.REPORTS_DIR, report_name)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# Backtest report - {ts}\n\n")
            f.write(f"**Orizzonte temporale:** {start_dt} / {end_dt}  \n")
            f.write(f"**Anni in simulazione:** {years}  \n")
            f.write(f"**CAGR:** {cagr:.2f}%  \n")
            f.write(f"**Total compound return:** {ptf.CompoundReturn * 100:.2f}%  \n")
            f.write(f"**Capitale iniziale:** {ptf.StartValue}  \n")
            f.write(f"**Capitale finale:** {ptf.TotValue:.2f}  \n\n")
            f.write(f"**Parametri:**\n")
            f.write(f"- initial_w: {initial_w}\n")
            f.write(f"- transac_cost_rate: {ptf.transactional_cost_rate}\n")
            f.write(f"- tax_rate: {ptf.tax_rate}\n")
            f.write(f"- rebalance_threshold: {ptf.rebalance_threshold}\n\n")
            f.write(f"**Output files:**\n")
            f.write(f"- {os.path.abspath(xlsx_path)}\n")
            f.write(f"- {os.path.abspath(delta_path)}\n")

        logger.info(f"Saved markdown report: {report_path}")

        # Try to plot (non-blocking); failures are ignored
        try:
            plt.semilogy(df_log.index,df_log['Compound Return'])
            plt.xlabel('Data')
            plt.ylabel('Compound Return %')
            plt.grid(True)
            plt.tight_layout()
            plt.show()
        except Exception:
            pass
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

    try:
        plt.semilogy(df_log.index,df_log['Compound Return'])
        plt.xlabel('Data')
        plt.ylabel('Compound Return %')
        plt.grid(True)
        plt.tight_layout()
        plt.show()
    except Exception:
        pass


if __name__ == '__main__':
    run_backtest()

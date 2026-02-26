import os
import shutil
from datetime import datetime
import json
import pandas as pd
import matplotlib.pyplot as plt
from report_writer_html import write_html_report
from report_writer_files import write_aux_files
from report_writer_md import write_markdown_report

def create_reports(ts: str, df_log: pd.DataFrame, df_log_delta: pd.DataFrame,
                   rebalance_explanations: list, rebalance_transactions: list,
                   ptf, cfg, verbose: bool = False):
    """Create markdown, html, xlsx and csv reports in `cfg.REPORTS_DIR`.

    This is extracted from the original `backtester.py` report block.
    """
    os.makedirs(cfg.REPORTS_DIR, exist_ok=True)
    xlsx_name = f"{ts}_{os.path.basename(cfg.OUTPUT_XLSX)}"
    delta_name = f"{ts}_{os.path.basename(cfg.OUTPUT_DELTA_XLSX)}"
    xlsx_path = os.path.join(cfg.REPORTS_DIR, xlsx_name)
    delta_path = os.path.join(cfg.REPORTS_DIR, delta_name)
    try:
        df_log.to_excel(xlsx_path)
        df_log_delta.to_excel(delta_path)
    except Exception:
        pass

    report_name = f"{ts}_backtest_report.md"
    report_path = os.path.join(cfg.REPORTS_DIR, report_name)

    # compute rebalance summary
    num_rebalances = len(rebalance_transactions)
    total_trade_volume = sum(tx.get('total_trade_value', 0.0) for tx in rebalance_transactions) if num_rebalances > 0 else 0.0
    asset_trade_totals = {}
    asset_net_delta = {}
    for tx in rebalance_transactions:
        for a, val in tx.get('trade_values', {}).items():
            asset_trade_totals[a] = asset_trade_totals.get(a, 0.0) + (val or 0.0)
        for a, d in tx.get('delta_notional', {}).items():
            asset_net_delta[a] = asset_net_delta.get(a, 0.0) + (d or 0.0)

    # Write XLSX/CSV auxiliary files (delegated)
    aux = write_aux_files(ts, df_log, df_log_delta, rebalance_transactions, cfg)
    xlsx_path = aux.get('xlsx_path')
    delta_path = aux.get('delta_path')
    trans_csv_path = aux.get('trans_csv_path')

    # Write markdown report (delegated)
    try:
        write_markdown_report(report_path, ts, df_log, df_log_delta, rebalance_explanations, rebalance_transactions, ptf, cfg, asset_trade_totals, xlsx_path, delta_path)
    except Exception:
        pass

    # Build interactive HTML report by delegating to report_writer_html.py
    try:
        html_path = report_path.replace('.md', '.html')
        html_path = write_html_report(html_path, ts, df_log, rebalance_explanations, rebalance_transactions, ptf, cfg, asset_trade_totals)
    except Exception:
        html_path = None

    # transactions CSV handled by write_aux_files

    # Copy latest files
    try:
        def safe_copy(src, dst_name):
            try:
                dst = os.path.join(cfg.REPORTS_DIR, dst_name)
                shutil.copyfile(src, dst)
            except Exception:
                pass

        safe_copy(report_path, 'latest_backtest_report.md')
        safe_copy(report_path.replace('.md', '.html'), 'latest_backtest_report.html')
        if trans_csv_path:
            safe_copy(trans_csv_path, 'latest_backtest_transactions.csv')
        safe_copy(xlsx_path, 'latest_output_ptf.xlsx')
        safe_copy(delta_path, 'latest_output_ptf_delta.xlsx')
    except Exception:
        pass

    return {
        'md': report_path,
        'html': html_path if 'html_path' in locals() else None,
        'xlsx': xlsx_path,
        'delta_xlsx': delta_path,
        'transactions_csv': trans_csv_path if 'trans_csv_path' in locals() else None,
    }

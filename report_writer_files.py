import os
import shutil
import pandas as pd
from typing import Dict, Optional


def write_aux_files(ts: str, df_log: pd.DataFrame, df_log_delta: pd.DataFrame,
                    rebalance_transactions: list, cfg) -> Dict[str, Optional[str]]:
    """Write XLSX, delta XLSX, transactions CSV and copy latest XLSX/CSV files.

    Returns dict with keys: xlsx_path, delta_path, trans_csv_path
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

    # Transactions CSV
    trans_csv_path = None
    try:
        trans_csv_name = f"{ts}_backtest_transactions.csv"
        trans_csv_path = os.path.join(cfg.REPORTS_DIR, trans_csv_name)
        rows = []
        for tx in rebalance_transactions:
            for a in tx.get('price', {}).keys():
                rows.append({
                    'date': tx.get('date'),
                    'asset': a,
                    'price': tx.get('price', {}).get(a, ''),
                    'delta_notional': tx.get('delta_notional', {}).get(a, 0.0),
                    'trade_value': tx.get('trade_values', {}).get(a, 0.0),
                    'total_trade_value': tx.get('total_trade_value', 0.0),
                    'transactional_cost': tx.get('transactional_cost', 0.0),
                    'tax': tx.get('tax', 0.0),
                    'pre_notional': tx.get('pre_notional', {}).get(a, '') if tx.get('pre_notional') else '',
                    'post_notional': tx.get('post_notional', {}).get(a, ''),
                    'pre_w': tx.get('pre_w', {}).get(a, '') if tx.get('pre_w') else '',
                    'post_w': tx.get('post_w', {}).get(a, ''),
                })
        if len(rows) > 0:
            df_tx = pd.DataFrame(rows)
            df_tx.to_csv(trans_csv_path, index=False)
        else:
            df_tx = pd.DataFrame(columns=['date','asset','price','delta_notional','trade_value','total_trade_value','transactional_cost','tax','pre_notional','post_notional','pre_w','post_w'])
            df_tx.to_csv(trans_csv_path, index=False)
    except Exception:
        trans_csv_path = None

    # Copy latest XLSX/CSV
    try:
        def safe_copy(src, dst_name):
            try:
                dst = os.path.join(cfg.REPORTS_DIR, dst_name)
                shutil.copyfile(src, dst)
            except Exception:
                pass

        if xlsx_path:
            safe_copy(xlsx_path, 'latest_output_ptf.xlsx')
        if delta_path:
            safe_copy(delta_path, 'latest_output_ptf_delta.xlsx')
        if trans_csv_path:
            safe_copy(trans_csv_path, 'latest_backtest_transactions.csv')
    except Exception:
        pass

    return {'xlsx_path': xlsx_path, 'delta_path': delta_path, 'trans_csv_path': trans_csv_path}

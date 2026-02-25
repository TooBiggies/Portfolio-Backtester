import os, sys, time
# ensure repo root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import backtester_config as cfg
from importlib import reload

import logging


def run_and_tag(tax_rate, tag):
    cfg.TAX_RATE = float(tax_rate)
    # run backtester
    import backtester
    reload(backtester)
    backtester.run_backtest()
    time.sleep(0.5)
    # find latest files
    rpt = cfg.REPORTS_DIR
    files = [os.path.join(rpt,f) for f in os.listdir(rpt) if f.endswith('_output_ptf.xlsx')]
    latest = max(files, key=os.path.getmtime)
    dst = os.path.join(rpt, f"tax_{str(tax_rate).replace('.','p')}_reb0_{tag}_output_ptf.xlsx")
    os.replace(latest, dst)
    files2 = [os.path.join(rpt,f) for f in os.listdir(rpt) if f.endswith('_output_ptf_delta.xlsx')]
    latest2 = max(files2, key=os.path.getmtime)
    dst2 = os.path.join(rpt, f"tax_{str(tax_rate).replace('.','p')}_reb0_{tag}_output_ptf_delta.xlsx")
    os.replace(latest2, dst2)
    print('Saved', dst, dst2)
    return dst, dst2

if __name__ == '__main__':
    # backup old value
    old_reb = cfg.REBALANCE_THRESHOLD
    try:
        cfg.REBALANCE_THRESHOLD = 0.0
        out_a, out_a2 = run_and_tag(0.0, 'runA')
        out_b, out_b2 = run_and_tag(0.26, 'runB')
        # quick analysis
        import pandas as pd
        da = pd.read_excel(out_a, index_col=0)
        db = pd.read_excel(out_b, index_col=0)
        print('Final TotValue 0.0:', da['TotValue'].dropna().iloc[-1])
        print('Final TotValue 0.26:', db['TotValue'].dropna().iloc[-1])
        print('Sum Taxes 0.0:', da['Taxes'].sum())
        print('Sum Taxes 0.26:', db['Taxes'].sum())
        diff = db['Taxes'].fillna(0) - da['Taxes'].fillna(0)
        diff.to_csv(os.path.join(cfg.REPORTS_DIR, 'tax_diff_reb0_0p26_minus_0p0.csv'))
        print('Wrote tax diff CSV')
    finally:
        cfg.REBALANCE_THRESHOLD = old_reb

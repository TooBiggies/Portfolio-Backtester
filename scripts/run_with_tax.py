import os, time, sys
# ensure repo root is on sys.path for local imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import backtester_config as cfg
from importlib import reload

def run_for_tax(tax_rate):
    # set tax rate in config
    cfg.TAX_RATE = float(tax_rate)
    # reload backtester module to ensure it reads updated cfg
    import backtester
    reload(backtester)
    # run
    backtester.run_backtest()
    # wait a moment for file timestamps
    time.sleep(1)
    # find latest output files in reports
    rpt = cfg.REPORTS_DIR
    files = [os.path.join(rpt,f) for f in os.listdir(rpt) if f.endswith('_output_ptf.xlsx')]
    if not files:
        raise SystemExit('No output_ptf.xlsx found in reports after run')
    latest = max(files, key=os.path.getmtime)
    # move/rename to include tax rate
    dst = os.path.join(rpt, f"tax_{str(tax_rate).replace('.','p')}_output_ptf.xlsx")
    os.replace(latest, dst)
    # same for delta
    files2 = [os.path.join(rpt,f) for f in os.listdir(rpt) if f.endswith('_output_ptf_delta.xlsx')]
    latest2 = max(files2, key=os.path.getmtime)
    dst2 = os.path.join(rpt, f"tax_{str(tax_rate).replace('.','p')}_output_ptf_delta.xlsx")
    os.replace(latest2, dst2)
    print('Saved', dst, dst2)

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('tax', type=float)
    args = p.parse_args()
    run_for_tax(args.tax)

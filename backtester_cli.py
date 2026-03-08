import argparse
from backtester_runner import run_backtest


def main():
    parser = argparse.ArgumentParser(description='Run portfolio backtester')
    parser.add_argument('--verbose', action='store_true', help='enable verbose debug output')
    parser.add_argument('--calcola-minusvalenze', action='store_true',
                        dest='calcola_minusvalenze',
                        help='attiva il riporto delle minusvalenze (art. 68 TUIR)')
    args = parser.parse_args()
    run_backtest(verbose=args.verbose, calcola_minusvalenze=args.calcola_minusvalenze)


if __name__ == '__main__':
    main()

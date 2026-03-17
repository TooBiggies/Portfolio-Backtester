import argparse
from backtester_runner import run_backtest


def main():
    parser = argparse.ArgumentParser(description='Run portfolio backtester')
    parser.add_argument('--verbose', action='store_true', help='enable verbose debug output')
    parser.add_argument('--calcola-minusvalenze', action='store_true',
                        dest='calcola_minusvalenze',
                        help='attiva il riporto delle minusvalenze (art. 68 TUIR)')
    parser.add_argument('--final-liquidation', action='store_true',
                        dest='final_liquidation',
                        help='vende tutte le posizioni all\'ultimo giorno della simulazione')
    args = parser.parse_args()
    run_backtest(verbose=args.verbose,
                 calcola_minusvalenze=args.calcola_minusvalenze,
                 final_liquidation=args.final_liquidation)


if __name__ == '__main__':
    main()

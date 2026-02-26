import argparse
from backtester_runner import run_backtest


def main():
    parser = argparse.ArgumentParser(description='Run portfolio backtester')
    parser.add_argument('--verbose', action='store_true', help='enable verbose debug output')
    args = parser.parse_args()
    run_backtest(verbose=args.verbose)


if __name__ == '__main__':
    main()
